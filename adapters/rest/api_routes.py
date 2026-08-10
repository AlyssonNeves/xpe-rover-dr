#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Declarative route table for the Rover REST input adapter."""

from adapters.rest.routing import RouteDispatcher
from app.models import CommandActions, CommandTargets


class ApiRoute(object):
    """Route metadata used by the transport adapter."""

    def __init__(self, method, pattern, name, target=None, action=None,
                 required_fields=None, allowed_fields=None):
        self.method = method
        self.pattern = tuple(pattern)
        self.name = name
        self.target = target
        self.action = action
        self.required_fields = tuple(required_fields or ())
        self.allowed_fields = tuple(allowed_fields or ())


class ApiRouteTable(object):
    """Resolves all command, lifecycle and gateway endpoints declaratively."""

    def __init__(self):
        self._dispatcher = RouteDispatcher()
        self._routes = {}
        self._register_commands()
        self._register_lifecycle()
        self._register_gateway()

    def add(self, route):
        self._routes[route.name] = route
        self._dispatcher.add(route.method, route.pattern, route.name)

    def resolve(self, method, path_parts):
        name, params = self._dispatcher.resolve(method, path_parts)
        if name is None:
            return None, None
        return self._routes[name], params or {}

    def _command(self, method, pattern, name, target, action,
                 required=None, allowed=None):
        self.add(ApiRoute(
            method, pattern, name, target, action,
            required_fields=required,
            allowed_fields=allowed
        ))

    def _register_commands(self):
        c = self._command
        self.add(ApiRoute("GET", ("api", "health"), "health"))
        c("GET", ("api", "state"), "state", CommandTargets.STATE,
          CommandActions.READ_ROVER_STATE)
        c("GET", ("api", "rover", "state"), "legacy_rover_state",
          CommandTargets.STATE, CommandActions.READ_ROVER_STATE)
        c("GET", ("api", "sensors"), "sensor_list",
          CommandTargets.SENSOR, CommandActions.LIST_SENSORS)
        c("GET", ("api", "sensors", "all"), "sensor_all",
          CommandTargets.SENSOR, CommandActions.READ_ALL_SENSORS)
        c("GET", ("api", "sensors", "{code}"), "sensor_read",
          CommandTargets.SENSOR, CommandActions.READ_SENSOR)
        c("GET", ("api", "sensors", "{code}", "modes"),
          "sensor_modes", CommandTargets.SENSOR,
          CommandActions.LIST_SENSOR_MODES)
        c("POST", ("api", "sensors", "{code}", "mode"),
          "sensor_mode", CommandTargets.SENSOR,
          CommandActions.CHANGE_SENSOR_MODE, required=("mode",),
          allowed=("mode",))

        c("GET", ("api", "motors"), "motor_list",
          CommandTargets.MOTOR, CommandActions.LIST_MOTORS)
        c("GET", ("api", "motors", "all"), "motor_all",
          CommandTargets.MOTOR, CommandActions.READ_ALL_MOTORS)
        c("GET", ("api", "motors", "{code}"), "motor_read",
          CommandTargets.MOTOR, CommandActions.READ_MOTOR)
        c("GET", ("api", "motor-commands"), "motor_commands",
          CommandTargets.MOTOR, CommandActions.LIST_MOTOR_COMMANDS)
        c("GET", ("api", "motor-commands", "{command_id}"),
          "motor_command", CommandTargets.MOTOR,
          CommandActions.READ_MOTOR_COMMAND)
        c("GET", ("api", "motors", "{code}", "commands"),
          "legacy_motor_commands_by_code", CommandTargets.MOTOR,
          CommandActions.LIST_MOTOR_COMMANDS)

        common = ("priority", "profile", "timeout_ms", "stop_action")
        c("POST", ("api", "motors", "{code}", "stop"),
          "motor_stop", CommandTargets.MOTOR,
          CommandActions.STOP_MOTOR, allowed=("stop_action",))
        c("POST", ("api", "motors", "{code}", "run-timed"),
          "motor_run_timed", CommandTargets.MOTOR,
          CommandActions.RUN_TIMED_MOTOR,
          required=("speed_sp", "time_sp"),
          allowed=("speed_sp", "time_sp") + common)
        c("POST", ("api", "motors", "{code}", "run-forever"),
          "motor_run_forever", CommandTargets.MOTOR,
          CommandActions.RUN_FOREVER_MOTOR, required=("speed_sp",),
          allowed=("speed_sp", "priority", "profile", "watchdog_ms",
                   "timeout_ms", "stop_action"))
        c("POST", ("api", "motors", "{code}", "run-direct"),
          "motor_run_direct", CommandTargets.MOTOR,
          CommandActions.RUN_DIRECT_MOTOR, required=("duty_cycle_sp",),
          allowed=("duty_cycle_sp", "priority", "watchdog_ms",
                   "timeout_ms", "stop_action"))
        c("POST", ("api", "motors", "{code}", "run-to-rel-pos"),
          "motor_run_rel", CommandTargets.MOTOR,
          CommandActions.RUN_TO_REL_POS_MOTOR,
          required=("speed_sp", "position_sp"),
          allowed=("speed_sp", "position_sp") + common)
        c("POST", ("api", "motors", "{code}", "run-to-abs-pos"),
          "motor_run_abs", CommandTargets.MOTOR,
          CommandActions.RUN_TO_ABS_POS_MOTOR,
          required=("speed_sp", "position_sp"),
          allowed=("speed_sp", "position_sp") + common)
        c("POST", ("api", "motors", "{code}", "cancel"),
          "motor_cancel", CommandTargets.MOTOR,
          CommandActions.CANCEL_MOTOR_COMMANDS)
        c("POST", ("api", "motors", "{code}", "reset"),
          "motor_reset", CommandTargets.MOTOR,
          CommandActions.RESET_MOTOR)
        c("POST", ("api", "motors", "sync"), "motor_sync",
          CommandTargets.MOTOR, CommandActions.RUN_SYNCHRONIZED_MOTORS,
          required=("commands",), allowed=("commands",))
        c("POST", ("api", "motors", "synchronized"),
          "legacy_motor_synchronized", CommandTargets.MOTOR,
          CommandActions.RUN_SYNCHRONIZED_MOTORS,
          required=("commands",), allowed=("commands",))
        c("POST", ("api", "motors", "stop-all"), "motor_stop_all",
          CommandTargets.MOTOR, CommandActions.STOP_ALL_MOTORS,
          allowed=("stop_action",))

        c("POST", ("api", "drive", "tank"), "drive_tank",
          CommandTargets.MOTOR, CommandActions.DRIVE_TANK,
          required=("left_speed_sp", "right_speed_sp"),
          allowed=("left_speed_sp", "right_speed_sp", "priority",
                   "profile"))
        c("POST", ("api", "drive", "stop"), "drive_stop",
          CommandTargets.MOTOR, CommandActions.STOP_DRIVE,
          allowed=("stop_action",))
        c("GET", ("api", "drive", "status"), "drive_status",
          CommandTargets.DRIVE, CommandActions.READ_DRIVE_STATUS)
        c("GET", ("api", "drive", "telemetry"), "drive_telemetry",
          CommandTargets.DRIVE, CommandActions.READ_DRIVE_TELEMETRY)
        c("POST", ("api", "drive", "odometry", "reset"),
          "drive_odometry_reset", CommandTargets.DRIVE,
          CommandActions.RESET_DRIVE_ODOMETRY,
          allowed=("x_mm", "y_mm", "heading_deg"))
        c("POST", ("api", "drive", "reset-odometry"),
          "legacy_drive_reset_odometry", CommandTargets.DRIVE,
          CommandActions.RESET_DRIVE_ODOMETRY,
          allowed=("x_mm", "y_mm", "heading_deg"))
        c("POST", ("api", "drive", "move-distance"), "drive_move",
          CommandTargets.DRIVE, CommandActions.MOVE_DRIVE_DISTANCE,
          required=("distance_mm", "speed_sp"),
          allowed=("distance_mm", "speed_sp", "stop_action",
                   "recover_on_stall"))
        c("POST", ("api", "drive", "rotate-angle"), "drive_rotate",
          CommandTargets.DRIVE, CommandActions.ROTATE_DRIVE_ANGLE,
          required=("angle_deg", "speed_sp"),
          allowed=("angle_deg", "speed_sp", "stop_action",
                   "recover_on_stall"))
        c("POST", ("api", "drive", "curve-radius"), "drive_curve",
          CommandTargets.DRIVE, CommandActions.CURVE_DRIVE_RADIUS,
          required=("radius_mm", "angle_deg", "speed_sp"),
          allowed=("radius_mm", "angle_deg", "speed_sp", "stop_action",
                   "recover_on_stall"))
        c("POST", ("api", "drive", "navigation-stop"),
          "drive_navigation_stop", CommandTargets.DRIVE,
          CommandActions.STOP_NAVIGATION, allowed=("stop_action",))

        c("GET", ("api", "controller"), "controller",
          CommandTargets.CONTROLLER,
          CommandActions.READ_CONTROLLER_STATUS)
        c("GET", ("api", "controller", "status"),
          "legacy_controller_status", CommandTargets.CONTROLLER,
          CommandActions.READ_CONTROLLER_STATUS)
        c("GET", ("api", "controller", "network"),
          "controller_network", CommandTargets.CONTROLLER,
          CommandActions.READ_CONTROLLER_NETWORK)
        c("GET", ("api", "controller", "battery"),
          "controller_battery", CommandTargets.CONTROLLER,
          CommandActions.READ_CONTROLLER_BATTERY)
        c("GET", ("api", "controller", "system"),
          "controller_system", CommandTargets.CONTROLLER,
          CommandActions.READ_CONTROLLER_SYSTEM)

    def _register_lifecycle(self):
        fields = ("token", "confirm")
        self.add(ApiRoute(
            "POST", ("api", "system", "shutdown"), "shutdown",
            allowed_fields=fields
        ))
        self.add(ApiRoute(
            "POST", ("api", "system", "restart"), "restart",
            allowed_fields=fields
        ))

    def _register_gateway(self):
        add = self.add
        add(ApiRoute("GET", ("api", "ev3dev2", "motor", "catalog"),
                     "gateway_catalog"))
        add(ApiRoute("GET", ("api", "ev3dev2", "motor", "objects"),
                     "gateway_objects"))
        add(ApiRoute("GET", ("api", "ev3dev2", "motor", "operations"),
                     "gateway_operations"))
        add(ApiRoute(
            "GET", ("api", "ev3dev2", "motor", "members", "{member}"),
            "gateway_member"
        ))
        add(ApiRoute(
            "GET", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                    "properties", "{property_name}"),
            "gateway_get_property"
        ))
        add(ApiRoute(
            "POST", ("api", "ev3dev2", "motor", "objects"),
            "gateway_create",
            allowed_fields=("class_name", "class", "args", "kwargs",
                            "object_id")
        ))
        add(ApiRoute(
            "POST", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                     "methods", "{method_name}"),
            "gateway_invoke", allowed_fields=("args", "kwargs")
        ))
        add(ApiRoute(
            "POST", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                     "properties", "{property_name}"),
            "gateway_set_property", required_fields=("value",),
            allowed_fields=("value",)
        ))
        add(ApiRoute(
            "DELETE", ("api", "ev3dev2", "motor", "objects",
                       "{object_id}"), "gateway_delete"
        ))
