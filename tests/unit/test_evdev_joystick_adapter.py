#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the first Linux evdev joystick adapter increment."""

import builtins

import pytest

from adapters.in_evdev_joystick import EvdevJoystickAdapter
from ports.joystick_port import JoystickPort


class FakeEvent(object):
    def __init__(self, event_type, code, value):
        self.type = event_type
        self.code = code
        self.value = value


class FakeAbsoluteInfo(object):
    def __init__(self, value):
        self.value = value


class FakeInputDevice(object):
    def __init__(self, path, name, events=None, fd=10, read_error=None,
                 absolute_values=None):
        self.path = path
        self.name = name
        self.events = list(events or [])
        self.fd = fd
        self.read_error = read_error
        self.absolute_values = dict(absolute_values or {
            0: 127, 1: 127, 3: 127
        })
        self.closed = False

    def absinfo(self, code):
        if code not in self.absolute_values:
            raise KeyError(code)
        return FakeAbsoluteInfo(self.absolute_values[code])

    def read(self):
        if self.read_error is not None:
            raise self.read_error
        events = list(self.events)
        self.events = []
        return events

    def read_one(self):
        if self.read_error is not None:
            raise self.read_error
        if not self.events:
            return None
        return self.events.pop(0)

    def close(self):
        self.closed = True


class FakeEvdevModule(object):
    def __init__(self, devices):
        self.devices = dict(devices)
        self.created = []

    def list_devices(self):
        return list(self.devices.keys())

    def InputDevice(self, path):
        source = self.devices[path]
        device = FakeInputDevice(
            path=source.path,
            name=source.name,
            events=list(source.events),
            fd=source.fd,
            read_error=source.read_error,
            absolute_values=source.absolute_values
        )
        self.created.append(device)
        return device


def test_adapter_implements_joystick_port():
    adapter = EvdevJoystickAdapter(evdev_module=FakeEvdevModule({}))

    assert isinstance(adapter, JoystickPort)


def test_open_selects_named_linux_input_device_and_closes_non_match():
    keyboard = FakeInputDevice("/dev/input/event0", "AT Keyboard", fd=10)
    gamepad = FakeInputDevice("/dev/input/event4", "Wireless Controller", fd=14)
    evdev_module = FakeEvdevModule({
        keyboard.path: keyboard,
        gamepad.path: gamepad
    })
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    opened_name = adapter.open()

    assert opened_name == "Wireless Controller"
    assert evdev_module.created[0].closed is True
    assert adapter.device.path == "/dev/input/event4"
    assert adapter.device.closed is False


def test_open_reports_when_configured_device_is_not_exposed_by_evdev():
    keyboard = FakeInputDevice("/dev/input/event0", "AT Keyboard")
    adapter = EvdevJoystickAdapter(
        device_name="Wireless Controller",
        auto_connect=False,
        evdev_module=FakeEvdevModule({keyboard.path: keyboard})
    )

    with pytest.raises(RuntimeError) as error:
        adapter.open()

    assert "Wireless Controller" in str(error.value)
    assert "automatic Bluetooth connection is disabled" in str(error.value)


def test_read_event_waits_for_descriptor_and_normalizes_evdev_values():
    gamepad = FakeInputDevice(
        "/dev/input/event4",
        "Wireless Controller",
        events=[FakeEvent(3, 1, 255)],
        fd=14
    )
    select_calls = []

    def fake_select(readers, writers, errors, timeout):
        select_calls.append((readers, writers, errors, timeout))
        return readers, [], []

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()

    event = adapter.read_event(0.05)

    assert event == {"type": 3, "code": 1, "value": 255}
    assert select_calls == [([14], [], [14], 0.05)]


def test_read_event_preserves_key_event_type_code_and_value():
    gamepad = FakeInputDevice(
        "/dev/input/event4",
        "Wireless Controller",
        events=[FakeEvent(1, 304, 1)],
        fd=14
    )

    def fake_select(readers, writers, errors, timeout):
        del writers, errors, timeout
        return readers, [], []

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()

    assert adapter.read_event(0.01) == {
        "type": 1, "code": 304, "value": 1
    }


def test_read_event_returns_none_on_timeout():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller", fd=14
    )

    def fake_select(readers, writers, errors, timeout):
        del readers, writers, errors, timeout
        return [], [], []

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()

    assert adapter.read_event(0.01) is None


def test_close_releases_the_open_input_device_and_is_idempotent():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller", fd=14
    )
    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad})
    )
    adapter.open()
    opened_device = adapter.device

    adapter.close()
    adapter.close()

    assert opened_device.closed is True
    assert adapter.device is None


def test_read_event_requires_an_open_device():
    adapter = EvdevJoystickAdapter(evdev_module=FakeEvdevModule({}))

    with pytest.raises(RuntimeError) as error:
        adapter.read_event(0)

    assert "not open" in str(error.value)


def test_missing_python_evdev_dependency_has_explicit_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "evdev":
            raise ImportError("evdev unavailable for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    adapter = EvdevJoystickAdapter(evdev_module=None)

    with pytest.raises(RuntimeError) as error:
        adapter.open()

    assert "python-evdev is not available" in str(error.value)


def test_empty_device_name_is_rejected():
    with pytest.raises(ValueError):
        EvdevJoystickAdapter(device_name="   ", evdev_module=FakeEvdevModule({}))


def test_exceptional_descriptor_is_reported_as_bluetooth_disconnect():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller", fd=14
    )

    def fake_select(readers, writers, errors, timeout):
        del readers, writers, timeout
        return [], [], errors

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()
    opened = adapter.device

    with pytest.raises(OSError) as error:
        adapter.read_event(0.01)

    assert "Bluetooth joystick connection lost" in str(error.value)
    assert opened.closed is True
    assert adapter.device is None


def test_kernel_read_error_closes_stale_device_and_reports_disconnect():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller", fd=14,
        read_error=OSError("No such device")
    )

    def fake_select(readers, writers, errors, timeout):
        del writers, errors, timeout
        return readers, [], []

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()
    opened = adapter.device

    with pytest.raises(OSError) as error:
        adapter.read_event(0.01)

    assert "No such device" in str(error.value)
    assert "Bluetooth joystick connection lost" in str(error.value)
    assert opened.closed is True
    assert adapter.device is None


def test_select_failure_is_normalized_as_connection_loss():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller", fd=14
    )

    def fake_select(readers, writers, errors, timeout):
        del readers, writers, errors, timeout
        raise OSError("bad file descriptor")

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        select_function=fake_select
    )
    adapter.open()

    with pytest.raises(OSError) as error:
        adapter.read_event(0.01)

    assert "Bluetooth joystick connection lost" in str(error.value)
    assert adapter.device is None


class RecordingInputStream(object):
    def __init__(self):
        self.writes = []
        self.flush_calls = 0

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        self.flush_calls += 1


class FakeBluetoothProcess(object):
    def __init__(self, returncode=0, output="Connection successful", on_create=None):
        self.returncode = returncode
        self.output = output
        self.terminated = False
        self.killed = False
        self.stdin = RecordingInputStream()
        if on_create is not None:
            on_create()

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        del timeout
        return self.output, None

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_is_available_checks_existing_evdev_node_without_leaving_it_open():
    gamepad = FakeInputDevice("/dev/input/event4", "Wireless Controller")
    evdev_module = FakeEvdevModule({gamepad.path: gamepad})
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    assert adapter.is_available() is True
    assert evdev_module.created[-1].closed is True

def test_open_uses_existing_device_without_running_bluetoothctl():
    gamepad = FakeInputDevice("/dev/input/event4", "Wireless Controller")
    calls = []
    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({gamepad.path: gamepad}),
        device_address="41:42:76:52:94:E8",
        popen_factory=lambda *args, **kwargs: calls.append((args, kwargs))
    )

    assert adapter.open() == "Wireless Controller"
    assert calls == []

def test_open_requests_bluetoothctl_connect_and_waits_for_evdev_node():
    evdev_module = FakeEvdevModule({})
    gamepad = FakeInputDevice("/dev/input/event4", "Wireless Controller")
    calls = []

    def make_process(args, **kwargs):
        calls.append((args, kwargs))
        evdev_module.devices[gamepad.path] = gamepad
        return FakeBluetoothProcess()

    adapter = EvdevJoystickAdapter(
        evdev_module=evdev_module,
        device_address="41:42:76:52:94:E8",
        passive_reconnect_seconds=0.0,
        popen_factory=make_process
    )

    assert adapter.open() == "Wireless Controller"
    assert calls[0][0] == ["bluetoothctl"]
    assert calls[0][1]["stdin"] is not None
    assert adapter.device.path == "/dev/input/event4"

def test_open_requires_bluetooth_address_when_auto_connect_is_enabled():
    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({}),
        device_address="", auto_connect=True
    )

    with pytest.raises(RuntimeError, match="device_address"):
        adapter.open()

def test_bluetoothctl_failure_is_reported_with_command_output():
    def make_process(args, **kwargs):
        del args, kwargs
        return FakeBluetoothProcess(
            returncode=1, output="Failed to connect: org.bluez.Error.Failed"
        )

    adapter = EvdevJoystickAdapter(
        evdev_module=FakeEvdevModule({}),
        device_address="41:42:76:52:94:E8",
        passive_reconnect_seconds=0.0,
        popen_factory=make_process
    )

    with pytest.raises(RuntimeError) as error:
        adapter.open()

    assert "bluetoothctl could not connect" in str(error.value)
    assert "org.bluez.Error.Failed" in str(error.value)


class AxisSelectiveFakeDevice(FakeInputDevice):
    def __init__(self, path, supported_axes, name="Wireless Controller"):
        values = dict((code, 127) for code in supported_axes)
        super(AxisSelectiveFakeDevice, self).__init__(
            path, name, absolute_values=values
        )


class MultipleMatchingEvdevModule(object):
    def __init__(self):
        self.created = []

    @staticmethod
    def list_devices():
        return [
            "/dev/input/event-touch",
            "/dev/input/event-motion",
            "/dev/input/event-gamepad"
        ]

    def InputDevice(self, path):
        axes = {
            "/dev/input/event-touch": (0,),
            "/dev/input/event-motion": (0, 1),
            "/dev/input/event-gamepad": (0, 1, 3)
        }[path]
        device = AxisSelectiveFakeDevice(path, axes)
        self.created.append(device)
        return device


def test_same_name_auxiliary_nodes_are_skipped_until_gamepad_axes_are_found():
    evdev_module = MultipleMatchingEvdevModule()
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    candidate = adapter._find_named_device()

    assert candidate.path == "/dev/input/event-gamepad"
    assert evdev_module.created[0].closed is True
    assert evdev_module.created[1].closed is True
    assert evdev_module.created[2].closed is False
    candidate.close()


def test_same_name_node_without_complete_traction_axes_is_not_available():
    touch = AxisSelectiveFakeDevice("/dev/input/event-touch", (0,))
    module = FakeEvdevModule({touch.path: touch})
    adapter = EvdevJoystickAdapter(evdev_module=module)

    assert adapter.is_available() is False
    assert module.created[-1].closed is True


def test_refresh_absolute_state_discards_queued_history_and_reads_current_axes():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller",
        events=[FakeEvent(3, 1, 42)],
        absolute_values={0: 130, 1: 120, 3: 140}
    )
    module = FakeEvdevModule({gamepad.path: gamepad})
    adapter = EvdevJoystickAdapter(evdev_module=module)
    adapter.open()

    snapshot = adapter.refresh_absolute_state((0, 1, 3))

    assert snapshot == {0: 130, 1: 120, 3: 140}
    assert adapter.device.events == []


def test_refresh_absolute_state_fails_explicitly_for_unreadable_axis():
    gamepad = FakeInputDevice(
        "/dev/input/event4", "Wireless Controller",
        absolute_values={0: 127, 1: 127, 3: 127}
    )
    module = FakeEvdevModule({gamepad.path: gamepad})
    adapter = EvdevJoystickAdapter(evdev_module=module)
    adapter.open()

    with pytest.raises(RuntimeError, match=r"axis code\(s\): 2"):
        adapter.refresh_absolute_state((0, 1, 2, 3))


def test_passive_reconnect_uses_appearing_evdev_node_before_bluetoothctl():
    class AppearingModule(object):
        def __init__(self):
            self.calls = 0
            self.created = []

        def list_devices(self):
            self.calls += 1
            if self.calls < 3:
                return []
            return ["/dev/input/event7"]

        def InputDevice(self, path):
            device = FakeInputDevice(path, "Wireless Controller")
            self.created.append(device)
            return device

    module = AppearingModule()
    popen_calls = []
    clock_values = iter([0.0, 0.0, 0.05, 0.1, 0.15])
    adapter = EvdevJoystickAdapter(
        evdev_module=module,
        device_address="AA:BB:CC:DD:EE:FF",
        connection_timeout_seconds=0.5,
        passive_reconnect_seconds=0.2,
        discovery_poll_seconds=0.01,
        popen_factory=lambda *args, **kwargs: popen_calls.append((args, kwargs)),
        monotonic_clock=lambda: next(clock_values)
    )

    assert adapter.open() == "Wireless Controller"
    assert popen_calls == []


def test_bluetooth_failure_includes_bluez_and_evdev_axis_diagnostics():
    touch = AxisSelectiveFakeDevice("/dev/input/event-touch", (0,))
    module = FakeEvdevModule({touch.path: touch})
    process = FakeBluetoothProcess(
        returncode=1,
        output="Failed to connect: org.bluez.Error.Failed"
    )
    adapter = EvdevJoystickAdapter(
        evdev_module=module,
        device_address="AA:BB:CC:DD:EE:FF",
        passive_reconnect_seconds=0.0,
        popen_factory=lambda *args, **kwargs: process
    )

    with pytest.raises(RuntimeError) as error_info:
        adapter.open()

    message = str(error_info.value)
    assert "BlueZ rejected" in message
    assert "event-touch axes=0" in message


class LegacyAbsInfo(FakeAbsoluteInfo):
    def __init__(self, value, minimum, maximum, fuzz, flat, resolution):
        super(LegacyAbsInfo, self).__init__(value)
        self.min = minimum
        self.max = maximum
        self.fuzz = fuzz
        self.flat = flat
        self.resolution = resolution


class LegacyInputApi(object):
    def __init__(self, device_axes):
        self.device_axes = device_axes
        self.calls = []

    def ioctl_capabilities(self, file_descriptor):
        self.calls.append(file_descriptor)
        axes = self.device_axes[file_descriptor]
        return {
            3: [
                (code, (value, 0, 255, 0, 0, 0))
                for code, value in sorted(axes.items())
            ]
        }


class LegacyEvdevDevice(object):
    def __init__(self, path, file_descriptor, name="Wireless Controller"):
        self.path = path
        self.fd = file_descriptor
        self.name = name
        self.closed = False

    def read(self):
        return []

    def read_one(self):
        return None

    def close(self):
        self.closed = True


class LegacyEvdev112Module(object):
    AbsInfo = LegacyAbsInfo

    def __init__(self, path_axes):
        self.paths = list(path_axes)
        self.device_axes = {}
        self.created = []
        self.path_descriptors = {}
        for index, path in enumerate(self.paths):
            file_descriptor = 100 + index
            self.path_descriptors[path] = file_descriptor
            self.device_axes[file_descriptor] = dict(path_axes[path])
        self._input = LegacyInputApi(self.device_axes)

    def list_devices(self):
        return list(self.paths)

    def InputDevice(self, path):
        device = LegacyEvdevDevice(path, self.path_descriptors[path])
        self.created.append(device)
        return device


def test_evdev_112_compatibility_selects_complete_gamepad_node():
    module = LegacyEvdev112Module({
        "/dev/input/event-touch": {0: 127},
        "/dev/input/event-motion": {0: 127, 1: 127},
        "/dev/input/event-gamepad": {0: 127, 1: 127, 3: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=module)

    candidate = adapter._find_named_device()

    assert candidate.path == "/dev/input/event-gamepad"
    assert module.created[0].closed is True
    assert module.created[1].closed is True
    assert module._input.calls == [100, 101, 102]
    candidate.close()


def test_evdev_112_snapshot_reads_fresh_ioctl_values_each_time():
    module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 127, 1: 127, 3: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=module)
    adapter.device = module.InputDevice("/dev/input/event4")
    fd = adapter.device.fd

    module.device_axes[fd].update({0: 130, 1: 120, 3: 140})
    first = adapter.refresh_absolute_state((0, 1, 3))
    module.device_axes[fd].update({0: 127, 1: 127, 3: 127})
    second = adapter.refresh_absolute_state((0, 1, 3))

    assert first == {0: 130, 1: 120, 3: 140}
    assert second == {0: 127, 1: 127, 3: 127}
    assert module._input.calls == [fd, fd]


def test_evdev_112_diagnostics_reports_actual_readable_axes():
    module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 127, 1: 127, 3: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=module)

    assert adapter._named_device_diagnostics() == (
        "Matching evdev node(s): /dev/input/event4 axes=0,1,3"
    )
