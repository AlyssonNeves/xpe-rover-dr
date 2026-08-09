import pytest

from app.commands.domain_handlers import CommandHandlerRegistry, DomainCommandHandler
from app.models import CommandResult, CommandTargets


def test_command_result_factories_and_serialization():
    assert CommandResult.ok({"x": 1}).to_dict() == {
        "success": True, "status_code": 200, "data": {"x": 1}
    }
    assert CommandResult.bad_request("bad").status_code == 400
    assert CommandResult.not_found("missing").status_code == 404
    assert CommandResult.method_not_allowed().status_code == 405
    assert CommandResult.internal_error().status_code == 500
    assert CommandResult.service_unavailable("down").status_code == 503
    assert set(CommandTargets.values()) == {"sensor", "motor", "controller", "rover", "drive"}


def test_domain_handler_registry_dispatches_and_rejects_duplicates():
    handler = DomainCommandHandler("sensor", lambda action, params: (action, params))
    registry = CommandHandlerRegistry([handler])
    assert registry.get("sensor").handle("read", {"code": "TMP"}) == (
        "read", {"code": "TMP"}
    )
    assert registry.get("missing") is None
    assert registry.targets() == ("sensor",)
    with pytest.raises(ValueError):
        CommandHandlerRegistry([handler, handler])
