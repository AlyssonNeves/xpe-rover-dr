#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP-independent route table for Rover-DR application commands."""

from adapters.rest.routing import GatewayRouter, parse_command_id
from app.models import CommandActions, CommandResult, CommandTargets


class CommandRoutes(object):
    """Maps normalized REST paths to application commands and gateway calls."""

    def __init__(self, command_service, ev3dev2_motor_gateway=None):
        self.command_service = command_service
        self.gateway = GatewayRouter(ev3dev2_motor_gateway)

    def route_get(self, path_parts):
        if path_parts == ["api", "health"]:
            return CommandResult.ok({"status": "ok"})

        result = self._route_gateway_get(path_parts)
        if result is not None:
            return result

        routes = {
            ("api", "rover", "state"): (
                CommandTargets.ROVER, CommandActions.READ_ROVER_STATE, None
            ),
            ("api", "drive", "status"): (
                CommandTargets.DRIVE, CommandActions.READ_DRIVE_STATUS, None
            ),
            ("api", "sensors"): (
                CommandTargets.SENSOR, CommandActions.LIST_SENSORS, None
            ),
            ("api", "sensors", "all"): (
                CommandTargets.SENSOR, CommandActions.READ_ALL_SENSORS, None
            ),
            ("api", "motors"): (
                CommandTargets.MOTOR, CommandActions.LIST_MOTORS, None
            ),
            ("api", "motors", "all"): (
                CommandTargets.MOTOR, CommandActions.READ_ALL_MOTORS, None
            ),
            ("api", "motor-commands"): (
                CommandTargets.MOTOR, CommandActions.LIST_MOTOR_COMMANDS, None
            ),
        }
        route = routes.get(tuple(path_parts))
        if route is not None:
            target, action, params = route
            return self.command_service.execute(target, action, params)

        if len(path_parts) == 3 and path_parts[:2] == ["api", "sensors"]:
            return self.command_service.execute(
                CommandTargets.SENSOR,
                CommandActions.READ_SENSOR,
                {"code": path_parts[2]}
            )

        if len(path_parts) == 3 and path_parts[:2] == ["api", "motor-commands"]:
            return self.command_service.execute(
                CommandTargets.MOTOR,
                CommandActions.GET_MOTOR_COMMAND,
                {"command_id": parse_command_id(path_parts[2])}
            )

        if (
            len(path_parts) == 4
            and path_parts[:2] == ["api", "motors"]
            and path_parts[3] == "commands"
        ):
            return self.command_service.execute(
                CommandTargets.MOTOR,
                CommandActions.LIST_MOTOR_COMMANDS,
                {"code": path_parts[2]}
            )

        if len(path_parts) == 3 and path_parts[:2] == ["api", "motors"]:
            return self.command_service.execute(
                CommandTargets.MOTOR,
                CommandActions.READ_MOTOR,
                {"code": path_parts[2]}
            )

        controller_routes = {
            ("api", "controller", "status"):
                CommandActions.READ_CONTROLLER_STATUS,
            ("api", "controller", "network"):
                CommandActions.READ_CONTROLLER_NETWORK,
            ("api", "controller", "battery"):
                CommandActions.READ_CONTROLLER_BATTERY,
            ("api", "controller", "system"):
                CommandActions.READ_CONTROLLER_SYSTEM,
        }
        controller_action = controller_routes.get(tuple(path_parts))
        if controller_action is not None:
            return self.command_service.execute(
                CommandTargets.CONTROLLER, controller_action
            )

        return CommandResult.not_found("Endpoint not found")

    def route_post(self, path_parts, body):
        result = self._route_gateway_post(path_parts, body)
        if result is not None:
            return result

        drive_routes = {
            ("api", "drive", "tank"): CommandActions.DRIVE_TANK,
            ("api", "drive", "stop"): CommandActions.STOP_DRIVE,
            ("api", "drive", "reset-odometry"):
                CommandActions.RESET_DRIVE_ODOMETRY,
            ("api", "drive", "move-distance"):
                CommandActions.MOVE_DRIVE_DISTANCE,
            ("api", "drive", "rotate-angle"):
                CommandActions.ROTATE_DRIVE_ANGLE,
            ("api", "drive", "curve-radius"):
                CommandActions.CURVE_DRIVE_RADIUS,
        }
        drive_action = drive_routes.get(tuple(path_parts))
        if drive_action is not None:
            return self.command_service.execute(
                CommandTargets.DRIVE, drive_action, body
            )

        if path_parts == ["api", "motors", "synchronized"]:
            return self.command_service.execute(
                CommandTargets.MOTOR,
                CommandActions.RUN_SYNCHRONIZED_MOTORS,
                body
            )

        if len(path_parts) == 4 and path_parts[:2] == ["api", "motors"]:
            action_map = {
                "stop": CommandActions.STOP_MOTOR,
                "run-timed": CommandActions.RUN_TIMED_MOTOR,
                "run-forever": CommandActions.RUN_FOREVER_MOTOR,
                "run-to-rel-pos": CommandActions.RUN_TO_REL_POS_MOTOR,
                "reset": CommandActions.RESET_MOTOR,
                "cancel": CommandActions.CANCEL_MOTOR_COMMANDS,
            }
            action = action_map.get(path_parts[3])
            if action is not None:
                params = dict(body)
                params["code"] = path_parts[2]
                return self.command_service.execute(
                    CommandTargets.MOTOR, action, params
                )

        return CommandResult.not_found("Endpoint not found")

    def route_delete(self, path_parts):
        if (
            len(path_parts) == 5
            and path_parts[:4] == ["api", "ev3dev2", "motor", "objects"]
        ):
            return self.gateway.call("delete", path_parts[4])
        return CommandResult.not_found("Endpoint not found")

    def _route_gateway_get(self, path_parts):
        if path_parts == ["api", "ev3dev2", "motor", "catalog"]:
            return self.gateway.call("catalog")
        if path_parts == ["api", "ev3dev2", "motor", "objects"]:
            return self.gateway.call("list_objects")
        if path_parts == ["api", "ev3dev2", "motor", "operations"]:
            return self.gateway.call("list_operations")
        if (
            len(path_parts) == 7
            and path_parts[:4] == ["api", "ev3dev2", "motor", "objects"]
            and path_parts[5] == "properties"
        ):
            return self.gateway.call(
                "get_property", path_parts[4], path_parts[6]
            )
        if (
            len(path_parts) == 5
            and path_parts[:4] == ["api", "ev3dev2", "motor", "members"]
        ):
            return self.gateway.call("module_value", path_parts[4])
        return None

    def _route_gateway_post(self, path_parts, body):
        if path_parts == ["api", "ev3dev2", "motor", "objects"]:
            return self.gateway.call(
                "create",
                body.get("class"),
                body.get("args"),
                body.get("kwargs"),
                body.get("object_id")
            )
        if (
            len(path_parts) == 7
            and path_parts[:4] == ["api", "ev3dev2", "motor", "objects"]
            and path_parts[5] == "methods"
        ):
            return self.gateway.call(
                "invoke", path_parts[4], path_parts[6],
                body.get("args"), body.get("kwargs")
            )
        if (
            len(path_parts) == 7
            and path_parts[:4] == ["api", "ev3dev2", "motor", "objects"]
            and path_parts[5] == "properties"
        ):
            if "value" not in body:
                return CommandResult.bad_request("Field 'value' is required")
            return self.gateway.call(
                "set_property", path_parts[4], path_parts[6], body["value"]
            )
        return None
