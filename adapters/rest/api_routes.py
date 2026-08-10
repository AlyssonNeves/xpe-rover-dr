#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Declarative route metadata for Rover-DR REST commands."""

from adapters.rest.routing import RouteDispatcher
from app.models import CommandActions, CommandTargets


class ApiRoute(object):
    """Route metadata independent from HTTP handler implementation."""

    def __init__(self, method, pattern, name, target=None, action=None,
                 kind="command"):
        self.method = method
        self.pattern = tuple(pattern)
        self.name = name
        self.target = target
        self.action = action
        self.kind = kind


class ApiRouteTable(object):
    """Central declaration of command and EV3Dev2 gateway endpoints."""

    def __init__(self):
        self._dispatcher = RouteDispatcher()
        self._routes = {}
        self._register_command_routes()
        self._register_gateway_routes()

    def add(self, route):
        self._routes[route.name] = route
        self._dispatcher.add(route.method, route.pattern, route.name)

    def resolve(self, method, path_parts):
        name, params = self._dispatcher.resolve(method, path_parts)
        if name is None:
            return None, None
        return self._routes[name], params or {}

    def _command(self, method, pattern, name, target, action):
        self.add(ApiRoute(method, pattern, name, target, action))

    def _register_command_routes(self):
        c = self._command
        c("GET", ("api", "health"), "health", None, None)
        c("GET", ("api", "rover", "state"), "rover_state",
          CommandTargets.ROVER, CommandActions.READ_ROVER_STATE)
        c("GET", ("api", "drive", "status"), "drive_status",
          CommandTargets.DRIVE, CommandActions.READ_DRIVE_STATUS)
        c("GET", ("api", "sensors"), "sensor_list",
          CommandTargets.SENSOR, CommandActions.LIST_SENSORS)
        c("GET", ("api", "sensors", "all"), "sensor_all",
          CommandTargets.SENSOR, CommandActions.READ_ALL_SENSORS)
        c("GET", ("api", "sensors", "{code}"), "sensor_read",
          CommandTargets.SENSOR, CommandActions.READ_SENSOR)
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
          CommandActions.GET_MOTOR_COMMAND)
        c("GET", ("api", "motors", "{code}", "commands"),
          "motor_commands_by_code", CommandTargets.MOTOR,
          CommandActions.LIST_MOTOR_COMMANDS)
        c("GET", ("api", "controller", "status"), "controller_status",
          CommandTargets.CONTROLLER, CommandActions.READ_CONTROLLER_STATUS)
        c("GET", ("api", "controller", "network"), "controller_network",
          CommandTargets.CONTROLLER, CommandActions.READ_CONTROLLER_NETWORK)
        c("GET", ("api", "controller", "battery"), "controller_battery",
          CommandTargets.CONTROLLER, CommandActions.READ_CONTROLLER_BATTERY)
        c("GET", ("api", "controller", "system"), "controller_system",
          CommandTargets.CONTROLLER, CommandActions.READ_CONTROLLER_SYSTEM)

        c("POST", ("api", "drive", "tank"), "drive_tank",
          CommandTargets.DRIVE, CommandActions.DRIVE_TANK)
        c("POST", ("api", "drive", "stop"), "drive_stop",
          CommandTargets.DRIVE, CommandActions.STOP_DRIVE)
        c("POST", ("api", "drive", "reset-odometry"), "drive_reset",
          CommandTargets.DRIVE, CommandActions.RESET_DRIVE_ODOMETRY)
        c("POST", ("api", "drive", "move-distance"), "drive_move",
          CommandTargets.DRIVE, CommandActions.MOVE_DRIVE_DISTANCE)
        c("POST", ("api", "drive", "rotate-angle"), "drive_rotate",
          CommandTargets.DRIVE, CommandActions.ROTATE_DRIVE_ANGLE)
        c("POST", ("api", "drive", "curve-radius"), "drive_curve",
          CommandTargets.DRIVE, CommandActions.CURVE_DRIVE_RADIUS)
        c("POST", ("api", "motors", "synchronized"), "motor_sync",
          CommandTargets.MOTOR, CommandActions.RUN_SYNCHRONIZED_MOTORS)
        c("POST", ("api", "motors", "{code}", "stop"), "motor_stop",
          CommandTargets.MOTOR, CommandActions.STOP_MOTOR)
        c("POST", ("api", "motors", "{code}", "run-timed"),
          "motor_run_timed", CommandTargets.MOTOR,
          CommandActions.RUN_TIMED_MOTOR)
        c("POST", ("api", "motors", "{code}", "run-forever"),
          "motor_run_forever", CommandTargets.MOTOR,
          CommandActions.RUN_FOREVER_MOTOR)
        c("POST", ("api", "motors", "{code}", "run-to-rel-pos"),
          "motor_run_rel", CommandTargets.MOTOR,
          CommandActions.RUN_TO_REL_POS_MOTOR)
        c("POST", ("api", "motors", "{code}", "reset"), "motor_reset",
          CommandTargets.MOTOR, CommandActions.RESET_MOTOR)
        c("POST", ("api", "motors", "{code}", "cancel"), "motor_cancel",
          CommandTargets.MOTOR, CommandActions.CANCEL_MOTOR_COMMANDS)

    def _register_gateway_routes(self):
        def add(method, pattern, name):
            self.add(ApiRoute(method, pattern, name, kind="gateway"))

        add("GET", ("api", "ev3dev2", "motor", "catalog"),
            "gateway_catalog")
        add("GET", ("api", "ev3dev2", "motor", "objects"),
            "gateway_objects")
        add("GET", ("api", "ev3dev2", "motor", "operations"),
            "gateway_operations")
        add("GET", ("api", "ev3dev2", "motor", "members", "{member}"),
            "gateway_member")
        add("GET", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                    "properties", "{property_name}"),
            "gateway_get_property")
        add("POST", ("api", "ev3dev2", "motor", "objects"),
            "gateway_create")
        add("POST", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                     "methods", "{method_name}"),
            "gateway_invoke")
        add("POST", ("api", "ev3dev2", "motor", "objects", "{object_id}",
                     "properties", "{property_name}"),
            "gateway_set_property")
        add("DELETE", ("api", "ev3dev2", "motor", "objects", "{object_id}"),
            "gateway_delete")
