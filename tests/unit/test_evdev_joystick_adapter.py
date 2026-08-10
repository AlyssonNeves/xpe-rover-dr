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


class FakeInputDevice(object):
    def __init__(self, path, name, events=None, fd=10, read_error=None):
        self.path = path
        self.name = name
        self.events = list(events or [])
        self.fd = fd
        self.read_error = read_error
        self.closed = False

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
            read_error=source.read_error
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


class FakeBluetoothProcess(object):
    def __init__(self, returncode=0, output="Connection successful", on_create=None):
        self.returncode = returncode
        self.output = output
        self.terminated = False
        self.killed = False
        if on_create is not None:
            on_create()

    def poll(self):
        return self.returncode

    def communicate(self):
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
        popen_factory=make_process
    )

    assert adapter.open() == "Wireless Controller"
    assert calls[0][0] == [
        "bluetoothctl", "connect", "41:42:76:52:94:E8"
    ]
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
        popen_factory=make_process
    )

    with pytest.raises(RuntimeError) as error:
        adapter.open()

    assert "bluetoothctl could not connect" in str(error.value)
    assert "org.bluez.Error.Failed" in str(error.value)
