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
    assert service.get_mode() == {"command": "LOCAL", "control": "MANUAL"}


def test_mode_selection_uses_ev3_selector_in_hardware_mode(monkeypatch):
    monkeypatch.setattr(assembly.rover_config, "HARDWARE_ENABLED", True)
    selector = object()
    monkeypatch.setattr(
        assembly, "Ev3CommandControlSelectorAdapter", lambda: selector
    )
    selected = {"command": "REMOTE", "control": None}

    class FakeModeService(object):
        def __init__(self, command_control_selector_port=None):
            assert command_control_selector_port is selector
        def select_command_control(self): return selected
        def get_mode(self): return dict(selected)

    monkeypatch.setattr(assembly, "OperationModeService", FakeModeService)
    service = assembly.select_operation_mode()
    assert service.get_mode() == selected


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
            "axis_max": 255,
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

    mode_service = assembly.OperationModeService()
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
    assert "drive_port" not in captured["joystick"]
    assert "motor_port" not in captured["joystick"]
    assert joystick_service in application.managed_services
