#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Composite motor port for full monitored infrastructure adapters."""

from ports.drive_motor_port import DriveMotorPort
from ports.guarded_motor_operation_port import GuardedMotorOperationPort
from ports.motor_command_port import MotorCommandPort
from ports.motor_command_query_port import MotorCommandQueryPort
from ports.motor_query_port import MotorQueryPort


class MotorPort(
        MotorQueryPort,
        MotorCommandPort,
        MotorCommandQueryPort,
        DriveMotorPort,
        GuardedMotorOperationPort):
    """Combines segregated contracts for adapters implementing every role."""

    pass
