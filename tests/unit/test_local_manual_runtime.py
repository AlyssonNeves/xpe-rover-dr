from adapters.out_local_manual_queries import (
    LocalManualControllerQueryAdapter,
    LocalManualMotorQueryAdapter,
    LocalManualSensorQueryAdapter,
)
from app.command_service import CommandService
from app.models import CommandActions as A, CommandTargets as T
from app.operation_mode_service import Controls, OperationModeService
from services.motor_state_store import MotorStateStore
import main as main_module


class FakeRestApi(object):
    def __init__(self, command_service, host, port, ev3dev2_motor_gateway=None):
        self.command_service = command_service
        self.host = host
        self.port = port
        self.gateway = ev3dev2_motor_gateway
        self.shutdown_callback = None
        self.restart_callback = None

    def set_shutdown_callback(self, callback):
        self.shutdown_callback = callback

    def set_restart_callback(self, callback):
        self.restart_callback = callback

    def start(self):
        return None

    def stop(self):
        return None


class FakeManualDrive(object):
    def close(self):
        return None


class FakeJoystickService(object):
    def start(self):
        return None

    def close(self):
        return None


def test_local_manual_sensor_query_uses_static_configured_metadata():
    adapter = LocalManualSensorQueryAdapter({
        "GYR": {"name": "Gyroscope", "address": "in3", "mode": "GYRO-ANG"}
    })
    assert adapter.list_sensors() == [{
        "code": "GYR", "name": "Gyroscope", "address": "in3",
        "connected": False
    }]
    sensor = adapter.read_sensor("GYR")
    assert sensor["monitoring"] is False
    assert sensor["value"] is None


def test_local_manual_motor_query_is_seeded_from_definitions():
    store = MotorStateStore()
    adapter = LocalManualMotorQueryAdapter(store, {
        "LLM": {"name": "Left", "address": "outA"}
    })
    motor = adapter.read_motor("LLM")
    assert motor["connected"] is False
    assert motor["speed_sp"] == 0
    assert motor["control_source"] == "local_manual"


def test_local_manual_motor_query_rejects_queue_writes():
    adapter = LocalManualMotorQueryAdapter(MotorStateStore(), {
        "LLM": {"name": "Left", "address": "outA"}
    })
    result = adapter.run_forever_motor("LLM", 300)
    assert result["accepted"] is False
    assert "LOCAL + MANUAL" in result["error"]
    assert adapter.list_commands() == []


def test_local_manual_controller_query_does_not_require_monitor_thread():
    adapter = LocalManualControllerQueryAdapter()
    assert adapter.read_controller_status()["mode"] == "local_manual"
    assert adapter.read_network_status()["mode"] == "on_demand"
    assert adapter.read_battery_status()["status"] == "unknown"


def test_command_service_makes_local_manual_rest_path_read_only():
    mode_service = OperationModeService()
    sensor = LocalManualSensorQueryAdapter({})
    motor = LocalManualMotorQueryAdapter(MotorStateStore(), {
        "LLM": {"name": "Left", "address": "outA"}
    })
    controller = LocalManualControllerQueryAdapter()
    service = CommandService(
        sensor, motor, controller,
        operation_mode_service=mode_service
    )

    assert service.execute(T.MOTOR, A.READ_MOTOR, {"code": "LLM"}).status_code == 200
    blocked = service.execute(
        T.MOTOR, A.RUN_FOREVER_MOTOR,
        {"code": "LLM", "speed_sp": 300}
    )
    assert blocked.status_code == 409
    assert service.execute(T.DRIVE, A.READ_DRIVE_STATUS).status_code == 409


def test_non_manual_mode_keeps_standard_command_authorization():
    mode_service = OperationModeService(control=Controls.AUTOMATIC)

    class WritableMotor(LocalManualMotorQueryAdapter):
        def run_forever_motor(self, *args, **kwargs):
            return {"accepted": True, "command_id": 1}

    motor = WritableMotor(MotorStateStore(), {
        "LLM": {"name": "Left", "address": "outA"}
    })
    service = CommandService(
        LocalManualSensorQueryAdapter({}), motor,
        LocalManualControllerQueryAdapter(),
        operation_mode_service=mode_service
    )
    result = service.execute(
        T.MOTOR, A.RUN_FOREVER_MOTOR,
        {"code": "LLM", "speed_sp": 300}
    )
    assert result.status_code == 200


def test_local_manual_builder_excludes_monitor_and_gateway_graph(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", False)
    monkeypatch.setattr(main_module, "RestApiServer", FakeRestApi)
    for name in ("SensorMonitor", "MotorMonitor", "ControllerMonitor"):
        monkeypatch.setattr(
            main_module, name,
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("monitor must not be constructed")
            )
        )
    monkeypatch.setattr(
        main_module, "Ev3Dev2MotorGateway",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("gateway must not be constructed")
        )
    )
    monkeypatch.setattr(main_module, "Ev3MotorHardwareAdapter", lambda **kwargs: object())
    monkeypatch.setattr(main_module, "ManualDriveService", lambda **kwargs: FakeManualDrive())

    application = main_module.build_application(
        operation_mode_service=OperationModeService()
    )
    assert application.monitors == []
    assert application.rest_api.gateway is None
    assert len(application.managed_services) == 1


def test_local_manual_builder_autowires_evdev_in_hardware_mode(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", True)
    monkeypatch.setattr(main_module, "RestApiServer", FakeRestApi)
    monkeypatch.setattr(main_module, "Ev3OperationStatusAdapter", lambda **kwargs: object())
    monkeypatch.setattr(main_module, "Ev3MotorHardwareAdapter", lambda **kwargs: object())
    manual = FakeManualDrive()
    monkeypatch.setattr(main_module, "ManualDriveService", lambda **kwargs: manual)

    joystick = object()
    captured = {}

    def make_evdev(device_name=None):
        captured["device_name"] = device_name
        return joystick

    def make_service(**kwargs):
        captured["joystick_port"] = kwargs["joystick_port"]
        captured["manual_drive_port"] = kwargs["manual_drive_port"]
        return FakeJoystickService()

    monkeypatch.setattr(main_module, "EvdevJoystickAdapter", make_evdev)
    monkeypatch.setattr(main_module, "JoystickControlService", make_service)

    application = main_module.build_application(
        operation_mode_service=OperationModeService()
    )
    assert captured["device_name"] == "Wireless Controller"
    assert captured["joystick_port"] is joystick
    assert captured["manual_drive_port"] is manual
    assert application.monitors == []


def test_local_manual_runtime_publishes_manual_motor_state_to_rest(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", False)
    monkeypatch.setattr(main_module, "RestApiServer", FakeRestApi)
    monkeypatch.setattr(main_module, "Ev3MotorHardwareAdapter", lambda **kwargs: object())
    captured = {}

    def make_manual(**kwargs):
        captured["publisher"] = kwargs["motor_state_publisher_port"]
        return FakeManualDrive()

    monkeypatch.setattr(main_module, "ManualDriveService", make_manual)
    application = main_module.build_application(
        operation_mode_service=OperationModeService()
    )
    captured["publisher"].publish_motor_state("LLM", {
        "connected": True, "speed_sp": 250, "running": True
    })
    result = application.rest_api.command_service.execute(
        T.MOTOR, A.READ_MOTOR, {"code": "LLM"}
    )
    assert result.status_code == 200
    assert result.data["speed_sp"] == 250
    assert result.data["running"] is True


def test_local_automatic_uses_existing_monitored_runtime(monkeypatch):
    monkeypatch.setattr(main_module.rover_config, "HARDWARE_ENABLED", False)
    mode = OperationModeService(control=Controls.AUTOMATIC)
    application = main_module.build_application(operation_mode_service=mode)
    assert len(application.monitors) == 3
