import pytest

from infrastructure.motor.registries import GuardedOperationRegistry, MotorCommandRegistry


def test_motor_command_registry_create_get_list_update_and_copy_isolation():
    registry = MotorCommandRegistry()
    created = registry.create({"command_id": 2, "motor_code": "RLM", "status": "QUEUED"})
    registry.create({"command_id": 1, "motor_code": "LLM", "status": "QUEUED"})
    created["status"] = "changed"
    assert registry.get(2)["status"] == "QUEUED"
    assert [x["command_id"] for x in registry.list()] == [1, 2]
    assert len(registry.list("LLM")) == 1
    assert registry.update(1, "RUNNING", started=True)["started"] is True
    assert registry.get("bad") is None
    assert registry.update(99, "X") is None


def test_guarded_operation_registry_reservation_conflict_and_release():
    registry = GuardedOperationRegistry()
    first = registry.reserve(["LLM"], "native", "op-1")
    assert first["status"] == "RUNNING"
    with pytest.raises(ValueError):
        registry.reserve(["LLM"], "other", "op-2")
    released = registry.release("op-1", status="COMPLETED")
    assert released["status"] == "COMPLETED"
    assert "LLM" not in registry.active_motor_codes
    assert registry.release("missing") is None
    registry.reserve(["RLM"], "native", "op-3")
    failed = registry.release("op-3", status="FAILED", error="boom", stop_errors=["stop"])
    assert failed["status"] == "STOP_FAILED"
    assert failed["error"] == "boom"
