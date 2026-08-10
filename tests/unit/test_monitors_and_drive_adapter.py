from unittest import mock

from adapters.out_drive_service import DriveServiceAdapter
from infrastructure.monitoring.controller_monitor import ControllerMonitor
from infrastructure.monitoring.sensor_monitor import SensorMonitor
from infrastructure.state.sensor_state_store import SensorStateStore


class Gyro(object):
    angle = 42


class GyroBackend(object):
    def __init__(self, connected=True):
        self.error = None if connected else "gyro unavailable"
        self.connected = connected

    def connect(self, definition):
        return Gyro() if self.connected else None

    def read_angle(self, sensor):
        return None if sensor is None else float(sensor.angle)


class FakeDrive(object):
    def __init__(self): self.calls = []
    def get_status(self): return {"status": "ok"}
    def reset_odometry(self, x, y, h): self.calls.append(("reset", x, y, h)); return {"x_mm": x}
    def drive_tank(self, l, r, priority=None, stop_action=None, watchdog_ms=None):
        self.calls.append(("tank", l, r, priority, stop_action, watchdog_ms)); return {"accepted": True}
    def move_distance(self, d, s, priority=None, stop_action=None, timeout_ms=None):
        return {"accepted": True, "distance_mm": d}
    def rotate_angle(self, a, s, priority=None, stop_action=None, timeout_ms=None):
        return {"accepted": True, "angle_deg": a}
    def curve_radius(self, r, a, s, priority=None, stop_action=None, timeout_ms=None):
        return {"accepted": True, "radius_mm": r}
    def stop(self, stop_action=None): return {"accepted": True, "stop_action": stop_action}


def test_sensor_monitor_connected_and_unavailable_gyro():
    store = SensorStateStore()
    monitor = SensorMonitor(store, interval_seconds=0.01, gyro_backend=GyroBackend(True))
    gyro = monitor.read_sensor("GYR")
    assert gyro["connected"] is True
    assert gyro["value"] == 42.0
    assert len(monitor.list_sensors()) == 5
    assert len(monitor.read_all_sensors()) == 5
    monitor.on_cycle()

    unavailable = SensorMonitor(
        SensorStateStore(), interval_seconds=0.01, gyro_backend=GyroBackend(False)
    )
    gyro = unavailable.read_sensor("GYR")
    assert gyro["connected"] is False
    assert gyro["source"] == "unavailable"
    assert gyro["error"] == "gyro unavailable"


def test_controller_monitor_refresh_and_ip_fallback():
    monitor = ControllerMonitor(interval_seconds=0.01)
    assert monitor.read_controller_status()["status"] == "available"
    assert "hostname" in monitor.read_network_status()
    assert monitor.read_battery_status()["status"] == "not_available"
    assert "python_version" in monitor.read_system_status()
    monitor.on_cycle()
    with mock.patch("infrastructure.monitoring.controller_monitor.socket.gethostbyname", side_effect=OSError()):
        assert monitor._resolve_ip("bad-host") == "0.0.0.0"


def test_drive_service_adapter_delegates_all_operations():
    drive = FakeDrive()
    adapter = DriveServiceAdapter(drive)
    assert adapter.get_status()["status"] == "ok"
    assert adapter.reset_odometry(1, 2, 3)["x_mm"] == 1
    assert adapter.drive_tank(100, -100, priority=5, stop_action="brake", watchdog_ms=1000)["accepted"]
    assert adapter.move_distance(100, 200)["distance_mm"] == 100
    assert adapter.rotate_angle(90, 200)["angle_deg"] == 90
    assert adapter.curve_radius(200, 45, 200)["radius_mm"] == 200
    assert adapter.stop("hold")["stop_action"] == "hold"
