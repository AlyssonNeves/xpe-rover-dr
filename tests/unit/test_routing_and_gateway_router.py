from adapters.rest.command_routes import CommandRoutes
from adapters.rest.routing import GatewayRouter, parse_command_id
from app.models import CommandResult


class Recorder(object):
    def __init__(self):
        self.calls = []

    def execute(self, target, action, params=None):
        self.calls.append((target, action, params))
        return CommandResult.ok({"target": target, "action": action, "params": params})


class Gateway(object):
    def catalog(self): return {"catalog": True}
    def list_objects(self): return []
    def list_operations(self): return []
    def module_value(self, name): return {"name": name}
    def get_property(self, oid, prop): return {"object_id": oid, "property": prop}
    def create(self, cls, args, kwargs, oid): return {"class": cls, "object_id": oid}
    def invoke(self, oid, method, args, kwargs): return {"method": method}
    def set_property(self, oid, prop, value): return {"value": value}
    def delete(self, oid): return {"deleted": oid}


def test_parse_command_id_and_gateway_router():
    assert parse_command_id("12") == 12
    assert parse_command_id("abc") == "abc"
    assert GatewayRouter(None).catalog().status_code == 503
    assert GatewayRouter(Gateway()).catalog().data["catalog"] is True


def test_command_routes_get_post_delete():
    recorder = Recorder()
    routes = CommandRoutes(recorder, Gateway())
    assert routes.route_get(["api", "health"]).status_code == 200
    assert routes.route_get(["api", "sensors"]).status_code == 200
    assert routes.route_get(["api", "sensors", "TMP"]).status_code == 200
    assert routes.route_get(["api", "motors", "LLM", "commands"]).status_code == 200
    assert routes.route_get(["api", "controller", "status"]).status_code == 200
    assert routes.route_get(["api", "ev3dev2", "motor", "catalog"]).data["catalog"] is True
    assert routes.route_get(["api", "unknown"]).status_code == 404

    assert routes.route_post(["api", "drive", "tank"], {"left_speed_sp": 1}).status_code == 200
    assert routes.route_post(["api", "motors", "LLM", "stop"], {}).status_code == 200
    assert routes.route_post(["api", "motors", "synchronized"], {"commands": []}).status_code == 200
    assert routes.route_post(["api", "ev3dev2", "motor", "objects"], {"class": "LargeMotor"}).status_code == 200
    missing = routes.route_post(
        ["api", "ev3dev2", "motor", "objects", "x", "properties", "position"], {}
    )
    assert missing.status_code == 400
    assert routes.route_delete(["api", "ev3dev2", "motor", "objects", "x"]).status_code == 200
    assert routes.route_delete(["api", "missing"]).status_code == 404
