import main as main_module
from bootstrap import rover_assembly as assembly


class FakeApplication(object):
    def __init__(self):
        self.started = False
        self.stopped = False
        self.waited = False
    def start(self): self.started = True
    def wait(self): self.waited = True
    def stop(self): self.stopped = True
    def is_restart_requested(self): return False


def test_mode_selection_defaults_without_physical_hardware(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", False)
    service = assembly.select_operation_mode()
    assert service.get_snapshot() == {
        "command": "LOCAL", "control": "MANUAL", "front": "NOSE",
        "drive": "DIFFERENTIAL", "centric": None
    }


def test_mode_selection_uses_ev3_selectors_and_remote_skips_local_setup(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    command_selector = object()
    local_selector = object()
    monkeypatch.setattr(
        assembly, "Ev3CommandControlSelectorAdapter", lambda: command_selector
    )
    monkeypatch.setattr(
        assembly, "Ev3LocalDriveSetupSelectorAdapter", lambda: local_selector
    )
    selected = {
        "command": "REMOTE", "control": None, "front": None,
        "drive": None, "centric": None
    }

    class FakeModeService(object):
        def __init__(self, command_control_selector_port=None,
                     local_drive_selector_port=None):
            assert command_control_selector_port is command_selector
            assert local_drive_selector_port is local_selector
            self.local_called = False
        def select_command_control(self): return dict(selected)
        def select_local_drive(self):
            self.local_called = True
            raise AssertionError("REMOTE must skip local setup")
        def get_snapshot(self): return dict(selected)

    monkeypatch.setattr(assembly, "OperationModeService", FakeModeService)
    service = assembly.select_operation_mode()
    assert service.get_snapshot() == selected
    assert service.local_called is False


def test_invalid_security_skips_ev3_alert_when_hardware_disabled(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", False)
    monkeypatch.setattr(
        assembly.rover_config, "validate_security_configuration",
        lambda: (_ for _ in ()).throw(RuntimeError("missing token"))
    )
    called = {"alert": False}
    monkeypatch.setattr(
        assembly, "StartupErrorNotifier",
        lambda *args, **kwargs: called.update(alert=True)
    )
    assert assembly.validate_startup_configuration() is False
    assert called["alert"] is False


def test_main_delegates_application_preparation_to_bootstrap(monkeypatch):
    app = FakeApplication()
    monkeypatch.setattr(
        main_module.rover_assembly, "prepare_rover_application", lambda: app
    )
    monkeypatch.setattr(main_module.signal, "signal", lambda *args: None)
    assert main_module.main() == 0
    assert app.started and app.waited and app.stopped


def test_build_application_adds_operation_status_in_hardware_mode(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    monkeypatch.setattr(
        assembly.rover_config, "get_joystick_config",
        lambda: {"device_name": "Wireless Controller"}
    )

    status_service = object()
    captured_status = {}

    def make_status(operation_mode_service=None, joystick_device_name=None):
        captured_status["mode"] = operation_mode_service
        captured_status["name"] = joystick_device_name
        return status_service

    monkeypatch.setattr(assembly, "Ev3OperationStatusAdapter", make_status)
    mode_service = assembly.OperationModeService()
    application = assembly.build_rover_application(
        operation_mode_service=mode_service
    )

    assert status_service in application.managed_services
    assert captured_status == {
        "mode": mode_service, "name": "Wireless Controller"
    }


def test_local_manual_joystick_is_wired_to_direct_manual_drive_path(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    monkeypatch.setattr(
        assembly.rover_config, "get_joystick_config",
        lambda: {
            "device_name": "Wireless Controller",
            "max_speed_sp": 600,
            "auxiliary_speed_sp": 400,
            "axis_center": 127,
            "axis_deadzone": 7,
            "axis_max": 255,
            "axis_response_intensity": 1.0,
            "left_auxiliary_motor_code": "LMM",
            "right_auxiliary_motor_code": "RMM",
            "poll_seconds": 0.02
        }
    )

    hardware = object()
    manual = object()
    joystick_service = object()
    captured = {}

    def make_hardware(**kwargs):
        captured["hardware"] = kwargs
        return hardware

    def make_manual(**kwargs):
        captured["manual"] = kwargs
        return manual

    def make_joystick(**kwargs):
        captured["joystick"] = kwargs
        return joystick_service

    monkeypatch.setattr(assembly, "Ev3MotorHardwareAdapter", make_hardware)
    monkeypatch.setattr(assembly, "ManualDriveService", make_manual)
    monkeypatch.setattr(assembly, "JoystickControlService", make_joystick)
    monkeypatch.setattr(
        assembly, "Ev3OperationStatusAdapter", lambda **kwargs: object()
    )

    mode_service = assembly.OperationModeService(
        drive=assembly.Drives.MECANUM, centric=assembly.Centrics.CHASSIS
    )
    application = assembly.build_rover_application(
        operation_mode_service=mode_service,
        joystick_port=object()
    )

    assert captured["manual"]["motor_hardware_port"] is hardware
    assert captured["manual"]["mecanum_config"] == assembly.rover_config.get_mecanum_config()
    assert captured["joystick"]["manual_drive_port"] is manual
    assert captured["joystick"]["drive_mode"] == "MECANUM"
    assert captured["joystick"]["centric"] == "CHASSIS"
    assert captured["joystick"]["mecanum_strafe_compensation"] == 1.1
    assert captured["joystick"]["axis_deadzone"] == 7
    assert captured["joystick"]["axis_response_intensity"] == 1.0
    assert "drive_port" not in captured["joystick"]
    assert "motor_port" not in captured["joystick"]
    assert joystick_service in application.managed_services


def test_local_mode_selection_runs_front_drive_centric_selector(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    command_selector = object()
    local_selector = object()
    monkeypatch.setattr(
        assembly, "Ev3CommandControlSelectorAdapter", lambda: command_selector
    )
    monkeypatch.setattr(
        assembly, "Ev3LocalDriveSetupSelectorAdapter", lambda: local_selector
    )
    service = assembly.OperationModeService(
        command_control_selector_port=type(
            "CommandSelector", (), {
                "select_mode": lambda self, command, control: {
                    "command": "LOCAL", "control": "MANUAL"
                }
            }
        )(),
        local_drive_selector_port=type(
            "LocalSelector", (), {
                "select_setup": lambda self, front, drive, centric: {
                    "front": "TAIL", "drive": "MECANUM", "centric": "CHASSIS"
                }
            }
        )()
    )
    monkeypatch.setattr(assembly, "OperationModeService", lambda **kwargs: service)
    selected_service = assembly.select_operation_mode()
    assert selected_service.get_snapshot() == {
        "command": "LOCAL", "control": "MANUAL", "front": "TAIL",
        "drive": "MECANUM", "centric": "CHASSIS"
    }


def test_field_selection_is_rejected_until_heading_pipeline_exists(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    service = assembly.OperationModeService(
        drive=assembly.Drives.MECANUM,
        centric=assembly.Centrics.FIELD
    )
    with __import__("pytest").raises(RuntimeError, match="live heading source"):
        assembly.build_local_manual_application(operation_mode_service=service)
