#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Exclusive motor reservation for native EV3 operations."""

import time


class MotorGuardedOperationManager(object):
    """Reserves motors and guarantees release/optional stop semantics."""

    def __init__(self, motor_definitions, registry, motor_repository,
                 preempt_callback, default_stop_action, logger):
        self.motor_definitions = motor_definitions
        self.registry = registry
        self.motor_repository = motor_repository
        self.preempt_callback = preempt_callback
        self.default_stop_action = default_stop_action
        self.logger = logger

    def begin(self, motor_codes, operation_name, operation_id):
        codes = self._validate_motor_codes(motor_codes)
        conflicts = [code for code in codes if self.registry.is_reserved(code)]
        if conflicts:
            raise ValueError(
                "Motors already reserved: {}".format(", ".join(conflicts))
            )
        for code in codes:
            self.preempt_callback(code, stop_running_command=True)
        return self.registry.reserve(
            operation_id=operation_id,
            motor_codes=codes,
            operation_name=operation_name,
            started_at=time.time()
        )

    def end(self, operation_id, status="COMPLETED", error=None, stop=False):
        record = self.registry.get(operation_id)
        if record is None:
            return None
        stop_errors = self._stop_reserved_motors(record, operation_id) if stop else []
        return self.registry.release(
            operation_id,
            status=status,
            error=error,
            completed_at=time.time(),
            stop_errors=stop_errors
        )

    def execute(self, motor_codes, operation_name, operation):
        operation_id = "sync-{}-{}".format(
            int(time.time() * 1000), id(operation)
        )
        self.begin(motor_codes, operation_name, operation_id)
        try:
            result = operation()
            self.end(operation_id, status="COMPLETED")
            return result
        except Exception as error:
            self.end(operation_id, status="FAILED", error=error, stop=True)
            raise

    def _validate_motor_codes(self, motor_codes):
        codes = []
        for code in motor_codes or []:
            if code not in self.motor_definitions:
                raise ValueError("Unknown motor code: {}".format(code))
            if code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("At least one configured motor is required.")
        return codes

    def _stop_reserved_motors(self, record, operation_id):
        errors = []
        for code in record["motor_codes"]:
            try:
                self.motor_repository.execute_stop(
                    code, self.default_stop_action
                )
            except Exception as exception:
                errors.append("{}: {}".format(code, exception))
                self.logger.error(
                    "Failed to stop motor {} while ending guarded operation "
                    "{}: {}".format(code, operation_id, exception)
                )
        return errors
