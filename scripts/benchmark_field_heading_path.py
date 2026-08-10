#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Host-side microbenchmark for the incremental FIELD control calculation."""

import statistics
import time

from adapters.out_heading_state import HeadingStateQueryAdapter
from app.operation_mode_service import Centrics, Drives, RoverOperationMode
from app.rover_config import DEFAULT_CONFIGURATION
from app.services.field_heading_reference_service import (
    FieldHeadingReferenceService
)
from app.services.joystick_control_service import JoystickControlService
from infrastructure.state.heading_state_store import HeadingStateStore


class _Joystick(object):
    @staticmethod
    def close():
        return None

    @staticmethod
    def is_available():
        return True


class _ManualDrive(object):
    @staticmethod
    def acquire(session_id, motor_codes=None):
        del session_id
        del motor_codes
        return {"success": True}

    @staticmethod
    def apply_mecanum_setpoint(*args, **kwargs):
        del args
        del kwargs
        return {"success": True}

    @staticmethod
    def emergency_stop(stop_action=None):
        del stop_action
        return {"success": True}

    @staticmethod
    def release(session_id, stop=True):
        del session_id
        del stop
        return {"success": True}


def _service(centric, heading_query_port=None):
    joystick = DEFAULT_CONFIGURATION.joystick
    service = JoystickControlService(
        joystick_port=_Joystick(),
        manual_drive_port=_ManualDrive(),
        device_name="benchmark",
        max_speed_sp=600,
        auxiliary_speed_sp=int(joystick["auxiliary_speed_sp"]),
        axis_center=int(joystick["axis_center"]),
        axis_deadzone=int(joystick["axis_deadzone"]),
        axis_max=int(joystick["axis_max"]),
        axis_response_intensity=float(
            joystick["axis_response_intensity"]
        ),
        left_auxiliary_motor_code=joystick[
            "left_auxiliary_motor_code"
        ],
        right_auxiliary_motor_code=joystick[
            "right_auxiliary_motor_code"
        ],
        poll_seconds=float(joystick["poll_seconds"]),
        connection_retry_seconds=float(
            joystick["connection_retry_seconds"]
        ),
        mecanum_strafe_compensation=float(
            DEFAULT_CONFIGURATION.mecanum["strafe_compensation"]
        ),
        operation_mode=RoverOperationMode(
            drive=Drives.MECANUM,
            centric=centric
        ),
        heading_query_port=heading_query_port
    )
    service._direction_x = 0.35
    service._direction_y = 0.80
    service._rotation_x = 0.15
    service._acquire_manual_session()
    service._update_mecanum()
    return service


def _measure(service, iterations, rounds):
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        for _ in range(iterations):
            service._update_mecanum()
        elapsed = time.perf_counter() - started
        samples.append((elapsed / iterations) * 1000000.0)
    return statistics.median(samples)


def main():
    iterations = 200000
    rounds = 5
    store = HeadingStateStore()
    store.update(37.25, time.monotonic())
    canonical_query = HeadingStateQueryAdapter(
        store, max_age_seconds=3600.0
    )
    field_query = FieldHeadingReferenceService(canonical_query)

    chassis = _service(Centrics.CHASSIS)
    field = _service(Centrics.FIELD, field_query)
    chassis_us = _measure(chassis, iterations, rounds)
    field_us = _measure(field, iterations, rounds)
    delta_us = field_us - chassis_us

    print("Host-side Mecanum calculation benchmark")
    print("Iterations per round: {0}; rounds: {1}".format(
        iterations, rounds
    ))
    print("CHASSIS median: {0:.3f} us/update".format(chassis_us))
    print("FIELD median:   {0:.3f} us/update".format(field_us))
    print("FIELD delta:    {0:.3f} us/update".format(delta_us))
    print("Delta vs 10 ms joystick poll: {0:.4f}%".format(
        max(0.0, delta_us) / 10000.0 * 100.0
    ))


if __name__ == "__main__":
    main()
