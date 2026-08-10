from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_rover_state_query import RoverStateQueryAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.state.motor_state_store import MotorStateStore
from app.services.rover_state_service import RoverStateService
from infrastructure.state.sensor_state_store import SensorStateStore
from tests.unit.fakes import FakeControllerPort, FakeMotorPort, FakeSensorPort


def test_sensor_store_isolated_copies_and_adapter_listing():
    store = SensorStateStore()
    store.update_sensor("TMP", {"code": "TMP", "name": "Temperature", "address": "in1", "connected": True})
    value = store.get_sensor("TMP")
    value["name"] = "changed"
    assert store.get_sensor("TMP")["name"] == "Temperature"
    monitor = type("M", (), {"state_store": store})()
    adapter = SensorMonitorAdapter(monitor, store)
    assert adapter.list_sensors()[0]["code"] == "TMP"
    assert adapter.read_sensor("UNKNOWN") is None
    store.clear()
    assert store.get_all_sensors() == []


def test_motor_store_and_adapter_delegation():
    store = MotorStateStore()
    store.update_motor("LLM", {"code": "LLM", "address": "outA"})
    fake = FakeMotorPort()
    fake.state_store = store
    adapter = MotorMonitorAdapter(fake, store)
    assert adapter.read_motor("LLM")["address"] == "outA"
    assert adapter.run_timed_motor("LLM", 100, 100)["accepted"] is True
    assert adapter.run_forever_motor("LLM", 100)["accepted"] is True
    assert adapter.run_to_rel_pos_motor("LLM", 100, 90)["accepted"] is True
    assert adapter.reset_motor("LLM")["accepted"] is True
    assert adapter.stop_motor("LLM")["accepted"] is True
    assert adapter.cancel_motor_commands("LLM")["accepted"] is True
    assert adapter.run_synchronized_motors([])["accepted"] is True
    assert adapter.execute_guarded_operation(["LLM"], "read", lambda: 7) == 7
    store.clear()
    assert store.get_all_motors() == []


def test_controller_store_adapter_and_rover_state_aggregation():
    store = ControllerStateStore()
    store.update_controller_status({"status": "ok"})
    store.update_network_status({"ip": "127.0.0.1"})
    store.update_battery_status({"voltage": 7.4})
    store.update_system_status({"platform": "test"})
    monitor = type("C", (), {"state_store": store})()
    adapter = ControllerMonitorAdapter(monitor, store)
    assert adapter.read_controller_status()["status"] == "ok"
    assert adapter.read_network_status()["ip"] == "127.0.0.1"
    assert adapter.read_battery_status()["voltage"] == 7.4
    assert adapter.read_system_status()["platform"] == "test"

    service = RoverStateService(FakeSensorPort(), FakeMotorPort(), FakeControllerPort())
    state = service.get_rover_state()
    assert len(state["sensors"]) == 2
    assert len(state["motors"]) == 2
    assert "timestamp" in state
    query = RoverStateQueryAdapter(service)
    assert query.get_rover_state()["controller"]["status"] == "ok"
    store.clear()
    assert store.get_controller_status() == {}


def test_rover_state_exposes_canonical_operation_snapshot():
    from app.operation_mode_service import Centrics, Drives, Fronts, OperationModeService

    mode_service = OperationModeService(
        front=Fronts.TAIL, drive=Drives.MECANUM, centric=Centrics.CHASSIS
    )
    service = RoverStateService(
        FakeSensorPort(), FakeMotorPort(), FakeControllerPort(),
        operation_mode_service=mode_service
    )
    assert service.get_rover_state()["operation_mode"] == {
        "command": "LOCAL", "control": "MANUAL", "front": "TAIL",
        "drive": "MECANUM", "centric": "CHASSIS"
    }
