#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for bounded evdev draining and Bluetooth disconnect detection."""

import subprocess

import pytest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from adapters.in_evdev_joystick import EvdevJoystickAdapter


class FakeEvent(object):
    def __init__(self, event_type, code, value):
        self.type = event_type
        self.code = code
        self.value = value


class FakeAbsoluteInfo(object):
    def __init__(self, value):
        self.value = value


class FakeDevice(object):
    def __init__(self):
        self.fd = 7
        self.read_calls = 0
        self.closed = False

    def absinfo(self, code):
        values = {0: 127, 1: 0, 3: 255}
        if code not in values:
            raise KeyError(code)
        return FakeAbsoluteInfo(values[code])

    def read(self):
        self.read_calls += 1
        return [FakeEvent(3, 5, self.read_calls)]

    def close(self):
        self.closed = True


class FakePoller(object):
    def __init__(self, mask):
        self.mask = mask
        self.unregistered = []

    def poll(self, timeout_ms):
        del timeout_ms
        return [(7, self.mask)]

    def unregister(self, file_descriptor):
        self.unregistered.append(file_descriptor)


def test_poll_hangup_is_reported_as_bluetooth_disconnect():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._poller = FakePoller(EvdevJoystickAdapter.POLLHUP)

    with pytest.raises(OSError, match="Bluetooth joystick connection lost"):
        adapter.read_event_batch(0.01, 64)


def test_event_drain_is_bounded_even_when_input_is_continuously_readable():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._poller = FakePoller(EvdevJoystickAdapter.POLLIN)
    adapter.MAX_DRAIN_SECONDS = 10.0

    events = adapter.read_event_batch(0.0, 64)

    assert adapter.device.read_calls == adapter.MAX_DRAIN_BATCHES
    assert events == [{
        "type": 3,
        "code": 5,
        "value": adapter.MAX_DRAIN_BATCHES
    }]




def test_event_drain_stops_when_total_drain_budget_is_reached():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._poller = FakePoller(EvdevJoystickAdapter.POLLIN)

    with mock.patch(
        "adapters.in_evdev_joystick.time.monotonic",
        side_effect=[0.0, 0.001, 0.004]
    ):
        events = adapter.read_event_batch(0.0, 64)

    assert adapter.device.read_calls == 2
    assert events == [{"type": 3, "code": 5, "value": 2}]

def test_event_batch_respects_max_events_and_retains_remainder():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._poller = FakePoller(0)
    adapter._append_coalesced([
        FakeEvent(1, 304, 1),
        FakeEvent(1, 304, 0),
        FakeEvent(3, 1, 0)
    ])

    first = adapter.read_event_batch(0.0, 2)
    second = adapter.read_event_batch(0.0, 2)

    assert first == [
        {"type": 1, "code": 304, "value": 1},
        {"type": 1, "code": 304, "value": 0}
    ]
    assert second == [{"type": 3, "code": 1, "value": 0}]


def test_event_batch_coalesces_axes_but_preserves_discrete_keys():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._poller = FakePoller(0)
    adapter._append_coalesced([
        FakeEvent(3, 1, 63),
        FakeEvent(1, 307, 1),
        FakeEvent(3, 1, 0),
        FakeEvent(1, 307, 0)
    ])

    events = adapter.read_event_batch(0.0, 64)

    assert events == [
        {"type": 1, "code": 307, "value": 1},
        {"type": 3, "code": 1, "value": 0},
        {"type": 1, "code": 307, "value": 0}
    ]

def test_current_traction_axes_are_seeded_before_live_input():
    adapter = EvdevJoystickAdapter()
    adapter._prime_absolute_state(FakeDevice())

    seeded = [
        (event.type, event.code, event.value)
        for event in adapter._event_buffer
    ]

    assert seeded == [
        (3, 0, 127),
        (3, 1, 0),
        (3, 3, 255)
    ]


class NamedFakeDevice(FakeDevice):
    def __init__(self, name="Wireless Controller"):
        super(NamedFakeDevice, self).__init__()
        self.name = name


class AppearingEvdevModule(object):
    def __init__(self):
        self.list_calls = 0
        self.devices = []

    def list_devices(self):
        self.list_calls += 1
        if self.list_calls == 1:
            return []
        return ["/dev/input/event7"]

    def InputDevice(self, path):
        del path
        device = NamedFakeDevice()
        self.devices.append(device)
        return device


class StaticEvdevModule(object):
    def __init__(self, paths):
        self.paths = list(paths)
        self.devices = []

    def list_devices(self):
        return list(self.paths)

    def InputDevice(self, path):
        del path
        device = NamedFakeDevice()
        self.devices.append(device)
        return device


def test_is_available_reports_named_evdev_device_and_closes_probe():
    evdev_module = StaticEvdevModule(["/dev/input/event7"])
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    assert adapter.is_available() is True
    assert evdev_module.devices[-1].closed is True


def test_is_available_reports_missing_named_evdev_device():
    adapter = EvdevJoystickAdapter(
        evdev_module=StaticEvdevModule([])
    )

    assert adapter.is_available() is False


class AxisSelectiveFakeDevice(NamedFakeDevice):
    def __init__(self, supported_axes, name="Wireless Controller"):
        super(AxisSelectiveFakeDevice, self).__init__(name=name)
        self.supported_axes = set(supported_axes)

    def absinfo(self, code):
        if code not in self.supported_axes:
            raise KeyError(code)
        return FakeAbsoluteInfo(127)


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
        device = AxisSelectiveFakeDevice(axes)
        device.path = path
        self.created.append(device)
        return device


def test_named_auxiliary_nodes_are_skipped_until_gamepad_axes_are_found():
    evdev_module = MultipleMatchingEvdevModule()
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    candidate = adapter._find_named_device()

    assert candidate.path == "/dev/input/event-gamepad"
    assert evdev_module.created[0].closed is True
    assert evdev_module.created[1].closed is True
    assert evdev_module.created[2].closed is False
    candidate.close()


def test_named_device_without_complete_traction_axes_is_not_available():
    class IncompleteEvdevModule(object):
        def __init__(self):
            self.device = None

        @staticmethod
        def list_devices():
            return ["/dev/input/event-touch"]

        def InputDevice(self, path):
            del path
            self.device = AxisSelectiveFakeDevice((0,))
            return self.device

    evdev_module = IncompleteEvdevModule()
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    assert adapter.is_available() is False
    assert evdev_module.device.closed is True


def test_passive_reconnect_opens_evdev_before_running_bluetoothctl():
    evdev_module = AppearingEvdevModule()
    adapter = EvdevJoystickAdapter(
        evdev_module=evdev_module,
        device_address="AA:BB:CC:DD:EE:FF",
        connection_timeout_seconds=0.5,
        passive_reconnect_seconds=0.2,
        discovery_poll_seconds=0.01
    )
    attempted = []
    adapter._execute_bluetooth_connect = lambda deadline: attempted.append(
        deadline
    )

    opened_name = adapter.open()

    assert opened_name == "Wireless Controller"
    assert attempted == []
    assert adapter.device is evdev_module.devices[-1]
    adapter.close()


def test_missing_device_triggers_bluetooth_connect_then_opens_evdev_device():
    evdev_module = AppearingEvdevModule()
    adapter = EvdevJoystickAdapter(
        evdev_module=evdev_module,
        device_address="AA:BB:CC:DD:EE:FF",
        connection_timeout_seconds=0.5,
        passive_reconnect_seconds=0.0,
        discovery_poll_seconds=0.01
    )
    attempted = []
    adapter._execute_bluetooth_connect = lambda deadline: attempted.append(deadline)

    opened_name = adapter.open()

    assert opened_name == "Wireless Controller"
    assert len(attempted) == 1
    assert adapter.device is evdev_module.devices[-1]
    adapter.close()


def test_missing_device_without_address_fails_without_running_bluetoothctl():
    adapter = EvdevJoystickAdapter(
        evdev_module=AppearingEvdevModule(),
        device_address=""
    )
    attempted = []
    adapter._execute_bluetooth_connect = lambda deadline: attempted.append(deadline)

    with pytest.raises(RuntimeError, match="no Bluetooth device_address"):
        adapter.open()

    assert attempted == []


def test_refresh_absolute_state_discards_history_and_returns_current_position():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()
    adapter._event_buffer.append(FakeEvent(3, 1, 42))

    snapshot = adapter.refresh_absolute_state((0, 1, 3))

    assert snapshot == {0: 127, 1: 0, 3: 255}
    assert list(adapter._event_buffer) == []
    assert adapter.device.read_calls == adapter.MAX_DRAIN_BATCHES


class DisconnectedAxisDevice(FakeDevice):
    def absinfo(self, code):
        del code
        raise OSError("device disconnected")


def test_refresh_absolute_state_preserves_bluetooth_disconnect_semantics():
    adapter = EvdevJoystickAdapter()
    adapter.device = DisconnectedAxisDevice()

    with pytest.raises(OSError, match="Bluetooth joystick connection lost"):
        adapter.refresh_absolute_state((1, 3))


def test_refresh_absolute_state_fails_explicitly_when_axis_is_unreadable():
    adapter = EvdevJoystickAdapter()
    adapter.device = FakeDevice()

    with pytest.raises(RuntimeError, match=r"axis code\(s\): 2"):
        adapter.refresh_absolute_state((0, 1, 2, 3))

    assert list(adapter._event_buffer) == []


class RecordingInputStream(object):
    def __init__(self):
        self.writes = []
        self.flush_calls = 0

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        self.flush_calls += 1


class HangingBluetoothProcess(object):
    def __init__(self, output="Attempting to connect"):
        self.returncode = None
        self.output = output
        self.terminated = False
        self.killed = False
        self.stdin = RecordingInputStream()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        del timeout
        return self.output, None


def test_running_bluetoothctl_is_stopped_when_required_evdev_node_appears():
    evdev_module = AppearingEvdevModule()
    process = HangingBluetoothProcess("Connection successful")
    adapter = EvdevJoystickAdapter(
        evdev_module=evdev_module,
        device_address="AA:BB:CC:DD:EE:FF",
        connection_timeout_seconds=0.5,
        passive_reconnect_seconds=0.0,
        discovery_poll_seconds=0.001
    )

    with mock.patch(
            "adapters.in_evdev_joystick.subprocess.Popen",
            return_value=process) as popen:
        opened_name = adapter.open()

    assert opened_name == "Wireless Controller"
    assert popen.call_args[0][0] == ["bluetoothctl"]
    assert popen.call_args[1]["stdin"] is subprocess.PIPE
    assert process.stdin.writes == [
        "connect AA:BB:CC:DD:EE:FF\n"
    ]
    assert process.stdin.flush_calls == 1
    assert process.terminated is True
    assert adapter.device is evdev_module.devices[-1]
    adapter.close()


def test_bluetooth_timeout_reports_concise_bluez_and_evdev_diagnostics():
    process = HangingBluetoothProcess(
        "\x1b[0;94m[bluetooth]\x1b[0m Attempting to connect to "
        "AA:BB:CC:DD:EE:FF Failed to connect: org.bluez.Error.Failed"
    )
    adapter = EvdevJoystickAdapter(
        evdev_module=StaticEvdevModule([]),
        device_address="AA:BB:CC:DD:EE:FF",
        connection_timeout_seconds=0.02,
        passive_reconnect_seconds=0.0,
        discovery_poll_seconds=0.005
    )

    with mock.patch(
            "adapters.in_evdev_joystick.subprocess.Popen",
            return_value=process):
        with pytest.raises(RuntimeError) as error_info:
            adapter.open()

    message = str(error_info.value)
    assert "timed out after 0.1 seconds" in message
    assert "org.bluez.Error.Failed" in message
    assert "No matching evdev node was observed" in message
    assert "Attempting to connect" not in message
    assert "\x1b[" not in message


def test_clean_process_output_removes_ansi_sequences():
    output = (
        "\x1b[0;94m[bluetooth]\x1b[0m "
        "Failed to connect: \x1b[0;91morg.bluez.Error.Failed\x1b[0m"
    )

    cleaned = EvdevJoystickAdapter._clean_process_output(output)

    assert cleaned == (
        "[bluetooth] Failed to connect: org.bluez.Error.Failed"
    )


def test_bluez_diagnosis_identifies_service_or_controller_loss():
    detail = (
        "Attempting to connect [DEL] Controller 00:11 ev3dev "
        "Waiting to connect to bluetoothd..."
    )

    diagnosis = EvdevJoystickAdapter._bluez_diagnosis(detail)

    assert "became unavailable" in diagnosis


def test_bluez_diagnosis_identifies_rejected_active_request():
    diagnosis = EvdevJoystickAdapter._bluez_diagnosis(
        "Failed to connect: org.bluez.Error.Failed"
    )

    assert "rejected" in diagnosis
    assert "org.bluez.Error.Failed" in diagnosis


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
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        return []

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
        device = LegacyEvdevDevice(
            path,
            self.path_descriptors[path]
        )
        self.created.append(device)
        return device


def test_evdev_112_compatibility_selects_complete_gamepad_node():
    evdev_module = LegacyEvdev112Module({
        "/dev/input/event-touch": {0: 127},
        "/dev/input/event-motion": {0: 127, 1: 127},
        "/dev/input/event-gamepad": {0: 127, 1: 127, 3: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    candidate = adapter._find_named_device()

    assert candidate.path == "/dev/input/event-gamepad"
    assert evdev_module.created[0].closed is True
    assert evdev_module.created[1].closed is True
    assert evdev_module.created[2].closed is False
    assert evdev_module._input.calls == [100, 101, 102]
    candidate.close()


def test_evdev_112_compatibility_reads_fresh_values_for_neutral_snapshot():
    evdev_module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 127, 1: 127, 3: 127}
    })
    device = evdev_module.InputDevice("/dev/input/event4")
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)
    adapter.device = device

    descriptor = device.fd
    evdev_module.device_axes[descriptor].update({0: 130, 1: 120, 3: 140})
    first_snapshot = adapter.refresh_absolute_state((0, 1, 3))
    evdev_module.device_axes[descriptor].update({0: 127, 1: 127, 3: 127})
    second_snapshot = adapter.refresh_absolute_state((0, 1, 3))

    assert first_snapshot == {0: 130, 1: 120, 3: 140}
    assert second_snapshot == {0: 127, 1: 127, 3: 127}
    assert len(evdev_module._input.calls) == 2


def test_evdev_112_compatibility_reports_missing_axis_explicitly():
    evdev_module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 127, 1: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)
    adapter.device = evdev_module.InputDevice("/dev/input/event4")

    with pytest.raises(RuntimeError, match=r"axis code\(s\): 3"):
        adapter.refresh_absolute_state((0, 1, 3))


def test_evdev_112_compatibility_seeds_current_axis_state():
    evdev_module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 126, 1: 128, 3: 129}
    })
    device = evdev_module.InputDevice("/dev/input/event4")
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    adapter._prime_absolute_state(device)

    assert [
        (event.type, event.code, event.value)
        for event in adapter._event_buffer
    ] == [
        (3, 0, 126),
        (3, 1, 128),
        (3, 3, 129)
    ]
    assert evdev_module._input.calls == [device.fd]


def test_evdev_112_diagnostics_reports_actual_readable_axes():
    evdev_module = LegacyEvdev112Module({
        "/dev/input/event4": {0: 127, 1: 127, 3: 127}
    })
    adapter = EvdevJoystickAdapter(evdev_module=evdev_module)

    diagnostics = adapter._named_device_diagnostics()

    assert diagnostics == (
        "Matching evdev node(s): /dev/input/event4 axes=0,1,3"
    )
    assert evdev_module.created[0].closed is True
