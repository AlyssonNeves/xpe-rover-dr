#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compatibility aggregate for segregated Rover motor contracts."""

from ports.guarded_motor_operation_port import GuardedMotorOperationPort
from ports.motor_command_port import MotorCommandPort
from ports.motor_command_query_port import MotorCommandQueryPort
from ports.motor_query_port import MotorQueryPort


class MotorPort(MotorQueryPort, MotorCommandPort, MotorCommandQueryPort,
                GuardedMotorOperationPort):
    """Legacy aggregate retained while callers migrate to focused ports."""
    pass
