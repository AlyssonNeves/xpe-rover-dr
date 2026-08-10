#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Linux evdev input adapter for a local Bluetooth game controller."""

import errno
import re
import select
import subprocess
import threading
import time
from collections import deque

from ports.joystick_port import JoystickPort


class BufferedInputEvent(object):
    """Small evdev-compatible event used to seed current absolute state."""

    def __init__(self, event_type, code, value):
        self.type = event_type
        self.code = code
        self.value = value


class _EvdevAbsoluteInfoCompatibility(object):
    """Reads live absolute-axis state across python-evdev API versions.

    python-evdev 1.1.2 does not expose ``InputDevice.absinfo()``. Its
    private C extension does expose ``ioctl_capabilities(fd)``, which issues
    fresh EVIOCGABS requests for every supported absolute axis. Keeping that
    version-specific detail here prevents the adapter from duplicating
    compatibility branches throughout discovery and neutral-state handling.
    """

    EV_ABS = 3

    def __init__(self, evdev_module):
        self.evdev_module = evdev_module

    def read_many(self, device, codes):
        """Returns current AbsInfo values keyed by requested axis code."""
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
        ioctl_capabilities = getattr(
            input_module, "ioctl_capabilities", None
        )
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
    """Discovers, connects and reads a named Bluetooth evdev controller."""

    MAX_DRAIN_BATCHES = 8
    MAX_DRAIN_SECONDS = 0.003
    BLUETOOTH_PROCESS_POLL_SECONDS = 0.1
    DEFAULT_DISCOVERY_POLL_SECONDS = 0.25
    DEFAULT_PASSIVE_RECONNECT_SECONDS = 4.0
    REQUIRED_TRACTION_AXIS_CODES = (0, 1, 3)
    # Linux poll(2) bit values are kept as portable fallbacks so the event-mask
    # logic remains unit-testable on hosts, such as Windows, without select.poll.
    POLLIN = getattr(select, "POLLIN", 0x001)
    POLLERR = getattr(select, "POLLERR", 0x008)
    POLLHUP = getattr(select, "POLLHUP", 0x010)
    POLLNVAL = getattr(select, "POLLNVAL", 0x020)
    POLL_ERROR_MASK = POLLERR | POLLHUP | POLLNVAL

    def __init__(self, device_name="Wireless Controller", evdev_module=None,
                 device_address="", auto_connect=True,
                 connection_timeout_seconds=10.0,
                 passive_reconnect_seconds=DEFAULT_PASSIVE_RECONNECT_SECONDS,
                 discovery_poll_seconds=DEFAULT_DISCOVERY_POLL_SECONDS):
        self.device_name = device_name
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
        self._absolute_info_compatibility = None
        self.device = None
        self._event_buffer = deque()
        self._poller = None
        self._connection_cancel_event = threading.Event()
        self._connection_process = None
        self._connection_lock = threading.RLock()

    def is_available(self):
        """Checks whether the named joystick is already exposed by evdev."""
        self._load_evdev_module()
        candidate = self._find_named_device()
        if candidate is None:
            return False
        candidate.close()
        return True

    def open(self):
        """Opens the joystick, asking BlueZ to connect it when necessary."""
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
                "Joystick '{0}' was not found and no Bluetooth device_address "
                "is configured.".format(self.device_name)
            )

        started_at = time.monotonic()
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
                "Joystick '{0}' did not appear in evdev after connecting "
                "Bluetooth device {1}. {2}".format(
                    self.device_name,
                    self.device_address,
                    self._named_device_diagnostics()
                )
            )
        return self._activate_device(candidate)

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

    def _find_named_device(self):
        """Returns the named evdev node that exposes all traction axes.

        Some Bluetooth gamepads, including PS4 controllers, may expose more
        than one ``/dev/input/event*`` node with the same display name. Touch,
        motion or auxiliary HID nodes must never be selected as the drive
        controller merely because their name also matches.
        """
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
        """Checks the exact absolute axes needed by Rover manual control."""
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
        """Describes matching evdev nodes and their readable traction axes."""
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
        self._configure_poller(candidate.fd)
        self._prime_absolute_state(candidate)
        return candidate.name

    def _wait_for_named_device(self, deadline):
        while not self._connection_cancel_event.is_set():
            candidate = self._find_named_device()
            if candidate is not None:
                return candidate
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return None
            self._connection_cancel_event.wait(
                min(self.discovery_poll_seconds, remaining)
            )
        raise RuntimeError("Bluetooth joystick connection attempt was cancelled.")

    def _execute_bluetooth_connect(self, deadline):
        """Connects BlueZ while treating evdev readiness as the authority.

        Some BlueZ/bluetoothctl combinations keep the one-shot process alive
        even after the HID device is connected. Rover must not wait for that
        process to exit when the required gamepad node is already usable.
        """
        try:
            process = subprocess.Popen(
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
            candidate, output, timed_out = (
                self._wait_for_bluetooth_or_evdev(process, deadline)
            )
        finally:
            with self._connection_lock:
                if self._connection_process is process:
                    self._connection_process = None

        if candidate is not None:
            return candidate

        detail = self._clean_process_output(output)
        bluez_diagnosis = self._bluez_diagnosis(detail)
        if timed_out:
            raise RuntimeError(
                "Bluetooth connection to {0} timed out after {1:.1f} "
                "seconds. {2} {3}".format(
                    self.device_address,
                    self.connection_timeout_seconds,
                    bluez_diagnosis,
                    self._named_device_diagnostics()
                )
            )

        if process.returncode != 0:
            raise RuntimeError(
                "bluetoothctl could not connect {0}. {1} {2}".format(
                    self.device_address,
                    bluez_diagnosis,
                    self._named_device_diagnostics()
                )
            )
        return None

    def _send_bluetooth_connect_command(self, process):
        """Sends connect through stdin for legacy interactive BlueZ."""
        input_stream = getattr(process, "stdin", None)
        if input_stream is None:
            raise RuntimeError(
                "bluetoothctl did not provide an interactive input stream."
            )
        try:
            input_stream.write(
                "connect {0}\n".format(self.device_address)
            )
            input_stream.flush()
        except (IOError, OSError, ValueError) as error:
            raise RuntimeError(
                "Unable to request Bluetooth connection to {0}: {1}".format(
                    self.device_address, error
                )
            )

    def _wait_for_bluetooth_or_evdev(self, process, deadline):
        """Waits for either a usable gamepad node or bluetoothctl exit."""
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

            remaining = deadline - time.monotonic()
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
        """Removes terminal control sequences from bluetoothctl output."""
        text = str(output or "")
        text = re.sub(
            r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])",
            "",
            text
        )
        return " ".join(text.replace("\r", "\n").strip().split())

    @staticmethod
    def _bluez_diagnosis(clean_output):
        """Returns a concise diagnosis for known legacy BlueZ failures."""
        output = str(clean_output or "")
        if ("Waiting to connect to bluetoothd" in output and
                "[DEL" in output and "Controller" in output):
            return (
                "BlueZ controller/service became unavailable during the "
                "connection attempt."
            )
        error_code = re.search(r"org\.bluez\.Error\.[A-Za-z]+", output)
        if error_code is not None:
            return (
                "BlueZ rejected the active connection request ({0})."
                .format(error_code.group(0))
            )
        return "BlueZ did not expose a usable HID gamepad node."

    @staticmethod
    def _collect_process_output(process):
        try:
            output, _ = process.communicate()
            return output or ""
        except (IOError, OSError):
            return ""

    @classmethod
    def _terminate_process(cls, process):
        if process.poll() is not None:
            return cls._collect_process_output(process)
        try:
            process.terminate()
            output, _ = process.communicate(timeout=0.5)
            return output or ""
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                output, _ = process.communicate()
                return output or ""
            except OSError:
                return ""

    def _prime_absolute_state(self, device):
        """Queues current traction-axis values before live events are read.

        evdev normally reports only changes after the device is opened. Seeding
        the three traction axes lets the application verify a genuinely neutral
        controller before enabling motion after startup or reconnection.
        """
        try:
            absolute_infos = self._read_absolute_infos(
                device, self.REQUIRED_TRACTION_AXIS_CODES
            )
        except (AttributeError, OSError, TypeError, ValueError):
            absolute_infos = {}
        for code in self.REQUIRED_TRACTION_AXIS_CODES:
            try:
                value = absolute_infos[code].value
            except (KeyError, AttributeError, TypeError):
                continue
            self._event_buffer.append(BufferedInputEvent(3, code, value))

    def refresh_absolute_state(self, axis_codes):
        """Returns a complete current-axis snapshot with no queued history.

        Startup movement is intentionally discarded. Every requested traction
        axis must be readable; otherwise initialization fails explicitly
        instead of remaining indefinitely in the neutral safety gate.
        """
        if self.device is None:
            raise RuntimeError("Joystick is not open.")

        requested_codes = tuple(axis_codes or ())
        self._event_buffer.clear()
        self._discard_device_events()
        snapshot = {}
        unreadable_codes = []
        try:
            absolute_infos = self._read_absolute_infos(
                self.device, requested_codes
            )
        except OSError as error:
            raise OSError(
                "Bluetooth joystick connection lost while reading axes "
                "{0}: {1}".format(
                    ", ".join(str(code) for code in requested_codes),
                    error
                )
            )
        except (AttributeError, TypeError, ValueError):
            absolute_infos = {}

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

    def _discard_device_events(self):
        """Drains the non-blocking kernel queue before taking a fresh snapshot."""
        for unused_index in range(self.MAX_DRAIN_BATCHES):
            try:
                events = self.device.read()
            except (BlockingIOError, OSError) as error:
                if getattr(error, "errno", None) in (
                        errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise OSError(
                    "Bluetooth joystick connection lost: {0}".format(error)
                )
            if not events:
                return

    def read_event_batch(self, timeout_seconds, max_events):
        """Returns one bounded, coalesced joystick event batch.

        The first event may wait up to ``timeout_seconds``. Once input becomes
        readable, draining is constrained by ``MAX_DRAIN_BATCHES`` and
        ``MAX_DRAIN_SECONDS`` so a noisy controller cannot monopolize the
        control thread. Axis events are coalesced by code while discrete key
        events are preserved in order.
        """
        if self.device is None:
            raise RuntimeError("Joystick is not open.")

        event_limit = max(1, int(max_events))
        wait_seconds = 0.0 if self._event_buffer else max(
            0.0, float(timeout_seconds)
        )
        self._read_available_batches(wait_seconds)

        events = []
        while self._event_buffer and len(events) < event_limit:
            event = self._event_buffer.popleft()
            events.append({
                "type": event.type,
                "code": event.code,
                "value": event.value
            })
        return events

    def _configure_poller(self, file_descriptor):
        if not hasattr(select, "poll"):
            self._poller = None
            return
        self._poller = select.poll()
        event_mask = self.POLLIN | self.POLL_ERROR_MASK
        self._poller.register(file_descriptor, event_mask)

    def _read_available_batches(self, timeout_seconds):
        """Drains promptly available evdev batches within one time budget."""
        if not self._wait_for_input(timeout_seconds):
            return

        started_at = time.monotonic()
        batches = 0
        while batches < self.MAX_DRAIN_BATCHES:
            try:
                events = self.device.read()
            except (BlockingIOError, OSError) as error:
                if getattr(error, "errno", None) in (
                    errno.EAGAIN, errno.EWOULDBLOCK
                ):
                    return
                raise OSError(
                    "Bluetooth joystick connection lost: {0}".format(error)
                )

            self._append_coalesced(events)
            batches += 1
            if time.monotonic() - started_at >= self.MAX_DRAIN_SECONDS:
                return
            if not self._wait_for_input(0.0):
                return

    def _wait_for_input(self, timeout_seconds):
        if self._poller is None:
            readable, _, exceptional = select.select(
                [self.device.fd],
                [],
                [self.device.fd],
                max(0.0, float(timeout_seconds))
            )
            if exceptional:
                raise OSError("Bluetooth joystick connection lost.")
            return bool(readable)

        timeout_ms = max(0, int(round(float(timeout_seconds) * 1000.0)))
        poll_events = self._poller.poll(timeout_ms)
        if not poll_events:
            return False

        readable = False
        for file_descriptor, event_mask in poll_events:
            if file_descriptor != self.device.fd:
                continue
            if event_mask & self.POLL_ERROR_MASK:
                raise OSError("Bluetooth joystick connection lost.")
            if event_mask & self.POLLIN:
                readable = True
        return readable

    def _append_coalesced(self, events):
        """Keeps discrete keys and only the newest value of each axis."""
        for event in events:
            if event.type not in (1, 3):
                continue
            if event.type == 3:
                self._event_buffer = deque(
                    buffered
                    for buffered in self._event_buffer
                    if not (
                        buffered.type == event.type
                        and buffered.code == event.code
                    )
                )
            self._event_buffer.append(event)

    def _close_device(self):
        if self.device is not None:
            try:
                if self._poller is not None:
                    self._poller.unregister(self.device.fd)
            except (KeyError, OSError, ValueError):
                pass
            try:
                self.device.close()
            finally:
                self.device = None
        self._poller = None
        self._event_buffer.clear()

    def close(self):
        self._connection_cancel_event.set()
        with self._connection_lock:
            process = self._connection_process
        if process is not None:
            self._terminate_process(process)
        self._close_device()
