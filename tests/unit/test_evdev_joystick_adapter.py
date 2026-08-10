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
    def __init__(self, path, name, events=None, fd=10):
        self.path = path
        self.name = name
        self.events = list(events or [])
        self.fd = fd
        self.closed = False

    def read_one(self):
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
            fd=source.fd
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
        evdev_module=FakeEvdevModule({keyboard.path: keyboard})
    )

    with pytest.raises(RuntimeError) as error:
        adapter.open()

    assert "Wireless Controller" in str(error.value)
    assert "Linux evdev" in str(error.value)


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
    assert select_calls == [([14], [], [], 0.05)]


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
