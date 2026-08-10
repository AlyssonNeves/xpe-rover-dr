#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared motor lifecycle vocabulary used by every Rover control path."""


class MotorLifecycleStates(object):
    SIMULATED = "SIMULATED"
    HARDWARE_READY = "HARDWARE_READY"
    HARDWARE_UNAVAILABLE = "HARDWARE_UNAVAILABLE"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    RESET = "RESET"
    CANCELLED = "CANCELLED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    STALLED = "STALLED"
    COMMAND_FAILED = "COMMAND_FAILED"
