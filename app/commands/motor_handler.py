#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Facade that routes motor queries and mutations to focused handlers."""

from app.commands.base_handler import BaseCommandHandler
from app.commands.motor_motion_handler import MotorMotionCommandHandler
from app.commands.motor_query_handler import MotorQueryCommandHandler
from app.commands.motor_validation import MotorParameterValidator


class MotorCommandHandler(BaseCommandHandler):
    """Routes motor queries and mutations to focused handlers."""

    def __init__(self, motor_query_port, motor_command_port=None,
                 motor_command_query_port=None, drive_motor_port=None):
        validator = MotorParameterValidator()
        self.query_handler = MotorQueryCommandHandler(
            motor_query_port, motor_command_query_port
        )
        self.motion_handler = MotorMotionCommandHandler(
            motor_command_port, drive_motor_port, validator
        )

    def execute(self, action, params):
        if action in self.query_handler.ACTIONS:
            return self.query_handler.execute(action, params)
        if action in self.motion_handler.ACTIONS:
            return self.motion_handler.execute(action, params)
        return self.unsupported("motor", action)
