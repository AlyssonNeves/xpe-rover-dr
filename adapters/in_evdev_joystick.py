#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Linux evdev input adapter for a local Bluetooth game controller."""

import errno
import select
import subprocess
import threading
import time
from collections import deque

from ports.joystick_port import JoystickPort


class _EvdevAbsoluteInfoCompatibility(object):
    """Reads current absolute-axis state across python-evdev API versions.

    ``python-evdev==1.1.2`` does not expose ``InputDevice.absinfo()`` on all
    supported ev3dev installations. Its private ``_input`` extension does
    expose ``ioctl_capabilities(fd)``, which performs a fresh EVIOCGABS read.
    Keeping that compatibility detail here lets discovery and safety snapshots
    share one implementation.
    """

    EV_ABS = 3

    def __init__(self, evdev_module):
        self.evdev_module = evdev_module

    def read_many(self, device, codes):
        requested_codes = tuple(int(code) for code in codes)
        native_reader = getattr(device, "absinfo", None)
        if callable(native_reader):
            return self._read_many_native(native_reader, requested_codes)
        return self._read_many_legacy(device, requested_codes)

    @staticmethod
    def _read_many_native(native_reader, requested_codes):
        values = {}
        for code in requested_codes:
            try:
                absolute_info = native_reader(code)
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            if absolute_info is not None:
                values[code] = absolute_info
        return values

    def _read_many_legacy(self, device, requested_codes):
        input_module = getattr(self.evdev_module, "_input", None)
        ioctl_capabilities = getattr(input_module, "ioctl_capabilities", None)
        if not callable(ioctl_capabilities):
            raise AttributeError(
                "python-evdev compatibility API "
                "_input.ioctl_capabilities is unavailable"
            )

        raw_capabilities = ioctl_capabilities(device.fd)
        requested = set(requested_codes)
        values = {}
        for entry in raw_capabilities.get(self.EV_ABS, ()):
            if not isinstance(entry, tuple) or len(entry) != 2:
                continue
            axis_code, raw_info = entry
            axis_code = int(axis_code)
            if axis_code in requested:
                values[axis_code] = self._coerce_absolute_info(raw_info)
        return values

    def _coerce_absolute_info(self, raw_info):
        if hasattr(raw_info, "value"):
            return raw_info
        absolute_info_type = getattr(self.evdev_module, "AbsInfo", None)
        if absolute_info_type is None:
            raise AttributeError(
                "python-evdev compatibility API AbsInfo is unavailable"
            )
        return absolute_info_type(*raw_info)


class EvdevJoystickAdapter(JoystickPort):
    """Discovers, connects and reads one usable Bluetooth gamepad node.

    A game controller may expose several ``/dev/input/event*`` devices with
    the same display name. Rover accepts only a node that can read the three
    traction axes required by manual control: ABS_X (0), ABS_Y (1) and
    ABS_RX (3). This prevents PS4 touch/motion nodes from being mistaken for
    the gamepad interface.
    """

    MAX_DRAIN_BATCHES = 8
    MAX_DRAIN_SECONDS = 0.003
    BLUETOOTH_PROCESS_POLL_SECONDS = 0.1
    DEFAULT_PASSIVE_RECONNECT_SECONDS = 4.0
    REQUIRED_TRACTION_AXIS_CODES = (0, 1, 3)
    POLL_ERROR_MASK = (
        getattr(select, "POLLERR", 0)
        | getattr(select, "POLLHUP", 0)
        | getattr(select, "POLLNVAL", 0)
    )

    def __init__(self, device_name="Wireless Controller", device_address="",
                 auto_connect=True, connection_timeout_seconds=10.0,
                 passive_reconnect_seconds=DEFAULT_PASSIVE_RECONNECT_SECONDS,
                 discovery_poll_seconds=0.25, evdev_module=None,
                 select_function=None, popen_factory=None,
                 monotonic_clock=None):
        self.device_name = str(device_name or "").strip()
        if not self.device_name:
            raise ValueError("device_name must not be empty.")
        self.device_address = str(device_address or "").strip()
        self.auto_connect = bool(auto_connect)
        self.connection_timeout_seconds = max(
            0.1, float(connection_timeout_seconds)
        )
        self.passive_reconnect_seconds = max(
            0.0, float(passive_reconnect_seconds)
        )
        self.discovery_poll_seconds = max(
            0.01, float(discovery_poll_seconds)
        )
        self.evdev_module = evdev_module
        self.select_function = select_function or select.select
        self.popen_factory = popen_factory or subprocess.Popen
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._absolute_info_compatibility = None
        self.device = None
        self._event_buffer = deque()
        self._poller = None
        self._use_poller = select_function is None and hasattr(select, "poll")
        self._connection_cancel_event = threading.Event()
        self._connection_process = None
        self._connection_lock = threading.RLock()

    def is_available(self):
        """Returns whether a usable gamepad node is already exposed."""
        self._load_evdev_module()
        candidate = self._find_named_device()
        if candidate is None:
            return False
        candidate.close()
        return True

    def open(self):
        """Opens the gamepad, preferring passive reconnection before BlueZ."""
        self._connection_cancel_event.clear()
        self._load_evdev_module()
        self._close_device()

        candidate = self._find_named_device()
        if candidate is not None:
            return self._activate_device(candidate)

        if not self.auto_connect:
            raise RuntimeError(
                "Joystick '{0}' was not found and automatic Bluetooth "
                "connection is disabled.".format(self.device_name)
            )
        if not self.device_address:
            raise RuntimeError(
                "Joystick '{0}' was not found and no Bluetooth "
                "device_address is configured.".format(self.device_name)
            )

        started_at = self.monotonic_clock()
        deadline = started_at + self.connection_timeout_seconds
        passive_deadline = min(
            deadline, started_at + self.passive_reconnect_seconds
        )
        if passive_deadline > started_at:
            candidate = self._wait_for_named_device(passive_deadline)
            if candidate is not None:
                return self._activate_device(candidate)

        candidate = self._execute_bluetooth_connect(deadline)
        if candidate is None:
            candidate = self._wait_for_named_device(deadline)
        if candidate is None:
            raise RuntimeError(
                "Joystick '{0}' did not expose a usable Linux evdev node "
                "after connecting Bluetooth device {1}. {2}".format(
                    self.device_name,
                    self.device_address,
                    self._named_device_diagnostics()
                )
            )
        return self._activate_device(candidate)

    def read_event_batch(self, timeout_seconds, max_events):
        """Returns one bounded, coalesced joystick event batch.

        The first event may wait up to ``timeout_seconds``. Once input is
        available, draining is bounded by both batch count and elapsed time so
        a noisy controller cannot monopolize the low-latency control thread.
        Absolute-axis values are coalesced by code while discrete key events
        retain their original order.
        """
        if self.device is None:
            raise RuntimeError("Joystick device is not open.")

        try:
            event_limit = max(1, int(max_events))
        except (TypeError, ValueError):
            raise ValueError("max_events must be a positive integer.")
        timeout = self._normalize_batch_timeout(timeout_seconds)
        wait_seconds = 0.0 if self._event_buffer else timeout
        self._read_available_batches(wait_seconds)

        events = []
        while self._event_buffer and len(events) < event_limit:
            event = self._event_buffer.popleft()
            events.append({
                "type": int(event.type),
                "code": int(event.code),
                "value": int(event.value)
            })
        return events

    def refresh_absolute_state(self, axis_codes):
        """Returns a fresh complete raw-axis snapshot.

        Queued movement history is discarded first. Every requested axis must
        be readable; an incomplete snapshot fails explicitly instead of
        leaving the post-connect neutral safety gate waiting indefinitely.
        """
        if self.device is None:
            raise RuntimeError("Joystick device is not open.")

        requested_codes = tuple(int(code) for code in (axis_codes or ()))
        self._event_buffer.clear()
        self._discard_device_events()
        try:
            absolute_infos = self._read_absolute_infos(
                self.device, requested_codes
            )
        except OSError as error:
            raise self._connection_lost(error)
        except (AttributeError, TypeError, ValueError):
            absolute_infos = {}

        snapshot = {}
        unreadable_codes = []
        for code in requested_codes:
            try:
                snapshot[code] = int(absolute_infos[code].value)
            except (KeyError, AttributeError, TypeError, ValueError):
                unreadable_codes.append(code)

        if unreadable_codes:
            raise RuntimeError(
                "Unable to read current joystick axis code(s): {0}.".format(
                    ", ".join(str(code) for code in unreadable_codes)
                )
            )
        return snapshot

    def close(self):
        """Cancels connection work and closes the current input device."""
        self._connection_cancel_event.set()
        self._cancel_connection_process()
        self._close_device()

    def _find_named_device(self):
        """Returns the matching node that exposes all required axes."""
        for path in self.evdev_module.list_devices():
            try:
                candidate = self.evdev_module.InputDevice(path)
            except (IOError, OSError):
                continue
            if (candidate.name == self.device_name and
                    self._supports_required_traction_axes(candidate)):
                return candidate
            candidate.close()
        return None

    def _supports_required_traction_axes(self, candidate):
        try:
            absolute_infos = self._read_absolute_infos(
                candidate, self.REQUIRED_TRACTION_AXIS_CODES
            )
            for code in self.REQUIRED_TRACTION_AXIS_CODES:
                int(absolute_infos[code].value)
        except (
                AttributeError, KeyError, OSError, TypeError, ValueError):
            return False
        return True

    def _read_absolute_infos(self, device, codes):
        if self._absolute_info_compatibility is None:
            self._absolute_info_compatibility = (
                _EvdevAbsoluteInfoCompatibility(self.evdev_module)
            )
        return self._absolute_info_compatibility.read_many(device, codes)

    def _named_device_diagnostics(self):
        """Describes matching nodes and the traction axes they expose."""
        summaries = []
        for path in self.evdev_module.list_devices():
            try:
                candidate = self.evdev_module.InputDevice(path)
            except (IOError, OSError):
                continue
            try:
                if candidate.name != self.device_name:
                    continue
                readable_axes = []
                try:
                    absolute_infos = self._read_absolute_infos(
                        candidate, self.REQUIRED_TRACTION_AXIS_CODES
                    )
                except (AttributeError, OSError, TypeError, ValueError):
                    absolute_infos = {}
                for code in self.REQUIRED_TRACTION_AXIS_CODES:
                    try:
                        int(absolute_infos[code].value)
                        readable_axes.append(code)
                    except (KeyError, AttributeError, TypeError, ValueError):
                        continue
                summaries.append(
                    "{0} axes={1}".format(
                        path,
                        ",".join(str(code) for code in readable_axes) or
                        "none"
                    )
                )
            finally:
                candidate.close()
        if not summaries:
            return "No matching evdev node was observed"
        return "Matching evdev node(s): {0}".format("; ".join(summaries))

    def _activate_device(self, candidate):
        self.device = candidate
        self._event_buffer.clear()
        self._configure_poller(candidate.fd)
        return candidate.name

    def _wait_for_named_device(self, deadline):
        while not self._connection_cancel_event.is_set():
            candidate = self._find_named_device()
            if candidate is not None:
                return candidate
            remaining = deadline - self.monotonic_clock()
            if remaining <= 0.0:
                return None
            self._connection_cancel_event.wait(
                min(self.discovery_poll_seconds, remaining)
            )
        raise RuntimeError("Bluetooth joystick connection attempt was cancelled.")

    def _execute_bluetooth_connect(self, deadline):
        """Runs interactive bluetoothctl while evdev readiness stays primary."""
        remaining = max(0.0, deadline - self.monotonic_clock())
        if remaining <= 0.0:
            raise RuntimeError("Bluetooth joystick connection timed out.")
        try:
            process = self.popen_factory(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
        except (IOError, OSError) as error:
            raise RuntimeError(
                "Unable to execute bluetoothctl: {0}".format(error)
            )

        with self._connection_lock:
            self._connection_process = process
        try:
            try:
                self._send_bluetooth_connect_command(process)
            except RuntimeError:
                self._terminate_process(process)
                raise
            candidate, output, timed_out = self._wait_for_bluetooth_or_evdev(
                process, deadline
            )
        finally:
            with self._connection_lock:
                if self._connection_process is process:
                    self._connection_process = None

        if candidate is not None:
            return candidate

        detail = self._clean_process_output(output)
        diagnosis = self._bluez_diagnosis(detail)
        if timed_out:
            raise RuntimeError(
                "Bluetooth connection to {0} timed out after {1:.1f} "
                "seconds. {2} bluetoothctl: {3}. {4}".format(
                    self.device_address,
                    self.connection_timeout_seconds,
                    diagnosis,
                    detail or "no diagnostic output",
                    self._named_device_diagnostics()
                )
            )
        if process.returncode != 0:
            raise RuntimeError(
                "bluetoothctl could not connect {0}. {1} "
                "bluetoothctl: {2}. {3}".format(
                    self.device_address,
                    diagnosis,
                    detail or "unknown error",
                    self._named_device_diagnostics()
                )
            )
        return None

    def _send_bluetooth_connect_command(self, process):
        input_stream = getattr(process, "stdin", None)
        if input_stream is None:
            raise RuntimeError(
                "bluetoothctl did not provide an interactive input stream."
            )
        try:
            input_stream.write("connect {0}\n".format(self.device_address))
            input_stream.flush()
        except (IOError, OSError, ValueError) as error:
            raise RuntimeError(
                "Unable to request Bluetooth connection to {0}: {1}".format(
                    self.device_address, error
                )
            )

    def _wait_for_bluetooth_or_evdev(self, process, deadline):
        while True:
            if self._connection_cancel_event.is_set():
                self._terminate_process(process)
                raise RuntimeError(
                    "Bluetooth joystick connection attempt was cancelled."
                )

            candidate = self._find_named_device()
            if candidate is not None:
                output = self._terminate_process(process)
                return candidate, output, False

            if process.poll() is not None:
                output = self._collect_process_output(process)
                candidate = self._find_named_device()
                return candidate, output, False

            remaining = deadline - self.monotonic_clock()
            if remaining <= 0.0:
                output = self._terminate_process(process)
                candidate = self._find_named_device()
                return candidate, output, True

            self._connection_cancel_event.wait(
                min(
                    self.discovery_poll_seconds,
                    self.BLUETOOTH_PROCESS_POLL_SECONDS,
                    remaining
                )
            )

    @staticmethod
    def _clean_process_output(output):
        return " ".join(str(output or "").strip().split())

    @staticmethod
    def _bluez_diagnosis(clean_output):
        output = str(clean_output or "")
        if ("Waiting to connect to bluetoothd" in output and
                "[DEL" in output and "Controller" in output):
            return (
                "BlueZ controller/service became unavailable during the "
                "connection attempt."
            )
        if "org.bluez.Error.Failed" in output:
            return "BlueZ rejected the active connection request."
        return "BlueZ did not expose a usable HID gamepad node."

    @staticmethod
    def _collect_process_output(process):
        try:
            output, _ = process.communicate()
            return output or ""
        except (IOError, OSError, TypeError, ValueError):
            return ""

    @classmethod
    def _terminate_process(cls, process):
        if process.poll() is not None:
            return cls._collect_process_output(process)
        try:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=0.5)
            except TypeError:
                output, _ = process.communicate()
            return output or ""
        except (IOError, OSError, subprocess.TimeoutExpired, ValueError):
            try:
                process.kill()
            except (IOError, OSError, AttributeError):
                pass
            return cls._collect_process_output(process)

    def _cancel_connection_process(self):
        with self._connection_lock:
            process = self._connection_process
        if process is not None:
            self._terminate_process(process)

    def _discard_device_events(self):
        """Drains queued kernel input before taking a fresh-axis snapshot."""
        read_many = getattr(self.device, "read", None)
        if not callable(read_many):
            return
        for unused_index in range(self.MAX_DRAIN_BATCHES):
            try:
                events = read_many()
            except (BlockingIOError, OSError) as error:
                if getattr(error, "errno", None) in (
                        errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise self._connection_lost(error)
            if not events:
                return

    def _configure_poller(self, file_descriptor):
        """Configures poll(2) for production while retaining test injection."""
        self._poller = None
        if not self._use_poller:
            return
        try:
            poller = select.poll()
            event_mask = getattr(select, "POLLIN", 1) | self.POLL_ERROR_MASK
            poller.register(file_descriptor, event_mask)
            self._poller = poller
        except (AttributeError, OSError, ValueError):
            self._poller = None

    def _read_available_batches(self, timeout_seconds):
        """Drains promptly available evdev batches within one time budget."""
        if not self._wait_for_input(timeout_seconds):
            return

        started_at = self.monotonic_clock()
        batches = 0
        while batches < self.MAX_DRAIN_BATCHES:
            try:
                events = self.device.read()
            except (BlockingIOError, OSError) as error:
                if getattr(error, "errno", None) in (
                        errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise self._connection_lost(error)

            if not events:
                return
            self._append_coalesced(events)
            batches += 1
            if self.monotonic_clock() - started_at >= self.MAX_DRAIN_SECONDS:
                return
            if not self._wait_for_input(0.0):
                return

    def _wait_for_input(self, timeout_seconds):
        timeout = max(0.0, float(timeout_seconds))
        if self._poller is None:
            try:
                readable, _, exceptional = self.select_function(
                    [self.device.fd], [], [self.device.fd], timeout
                )
            except (IOError, OSError) as error:
                raise self._connection_lost(error)
            if exceptional:
                raise self._connection_lost(
                    OSError("evdev descriptor reported an exceptional state")
                )
            return bool(readable)

        try:
            timeout_ms = max(0, int(round(timeout * 1000.0)))
            poll_events = self._poller.poll(timeout_ms)
        except (IOError, OSError) as error:
            raise self._connection_lost(error)
        if not poll_events:
            return False

        readable = False
        for file_descriptor, event_mask in poll_events:
            if file_descriptor != self.device.fd:
                continue
            if event_mask & self.POLL_ERROR_MASK:
                raise self._connection_lost(
                    OSError("evdev descriptor reported a disconnect state")
                )
            if event_mask & getattr(select, "POLLIN", 1):
                readable = True
        return readable

    def _append_coalesced(self, events):
        """Preserves keys while keeping only the newest value of each axis."""
        for event in events or ():
            event_type = int(event.type)
            if event_type not in (1, 3):
                continue
            if event_type == 3:
                self._event_buffer = deque(
                    buffered
                    for buffered in self._event_buffer
                    if not (
                        int(buffered.type) == event_type and
                        int(buffered.code) == int(event.code)
                    )
                )
            self._event_buffer.append(event)

    def _close_device(self):
        device = self.device
        self.device = None
        if device is not None:
            try:
                if self._poller is not None:
                    self._poller.unregister(device.fd)
            except (AttributeError, KeyError, OSError, ValueError):
                pass
            try:
                device.close()
            finally:
                self._poller = None
                self._event_buffer.clear()
        else:
            self._poller = None
            self._event_buffer.clear()

    def _connection_lost(self, error):
        """Releases the stale descriptor and returns a clear disconnect error."""
        try:
            self._close_device()
        except (IOError, OSError):
            self.device = None
            self._poller = None
            self._event_buffer.clear()
        return OSError(
            "Bluetooth joystick connection lost: {0}".format(error)
        )

    def _load_evdev_module(self):
        if self.evdev_module is not None:
            return
        try:
            import evdev
        except ImportError as error:
            raise RuntimeError(
                "python-evdev is not available: {0}".format(error)
            )
        self.evdev_module = evdev
        self._absolute_info_compatibility = None

    @staticmethod
    def _normalize_batch_timeout(timeout_seconds):
        try:
            return max(0.0, float(timeout_seconds))
        except (TypeError, ValueError):
            raise ValueError("timeout_seconds must be numeric.")
