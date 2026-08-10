#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-level motor command execution and native EV3 profile mapping."""


class MotorCommandExecutor(object):
    """Executes one already-validated command against the motor repository."""

    def __init__(self, motor_repository, actions, hardware_available,
                 hardware_error, default_stop_action, ramp_up_ms,
                 ramp_down_ms, direct_profile, ramp_up_profile,
                 ramp_down_profile, ramp_up_down_profile):
        self.motor_repository = motor_repository
        self.actions = actions
        self.hardware_available = hardware_available
        self.hardware_error = hardware_error
        self.default_stop_action = default_stop_action
        self.ramp_up_ms = ramp_up_ms
        self.ramp_down_ms = ramp_down_ms
        self.direct_profile = direct_profile
        self.ramp_up_profile = ramp_up_profile
        self.ramp_down_profile = ramp_down_profile
        self.ramp_up_down_profile = ramp_up_down_profile

    def execute(self, motor_code, action, parameters):
        if not self.hardware_available():
            return {
                "executed": False,
                "success": True,
                "hardware_error": self.hardware_error()
            }
        profile = parameters.get("profile", self.direct_profile)
        result = self._dispatch(motor_code, action, parameters, profile)
        return {
            "executed": True,
            "success": result.get("success", False),
            "hardware_error": result.get("hardware_error")
        }

    def _dispatch(self, motor_code, action, parameters, profile):
        dispatchers = {
            self.actions.STOP: self._stop,
            self.actions.RUN_TIMED: self._run_timed,
            self.actions.RUN_FOREVER: self._run_forever,
            self.actions.RUN_DIRECT: self._run_direct,
            self.actions.RUN_TO_REL_POS: self._run_to_rel_pos,
            self.actions.RUN_TO_ABS_POS: self._run_to_abs_pos,
            self.actions.RESET: self._reset
        }
        handler = dispatchers.get(action)
        if handler is None:
            return {
                "success": False,
                "hardware_error": "Unsupported motor command."
            }
        return handler(motor_code, parameters, profile)

    def _stop(self, motor_code, parameters, profile):
        del profile
        return self.motor_repository.execute_stop(
            motor_code,
            parameters.get("stop_action", self.default_stop_action)
        )

    def _run_timed(self, motor_code, parameters, profile):
        configured = self.configure_profile(
            motor_code, profile, parameters.get("stop_action")
        )
        if not configured.get("success"):
            return configured
        return self.motor_repository.execute_run_timed(
            motor_code, parameters.get("speed_sp"), parameters.get("time_sp")
        )

    def _run_forever(self, motor_code, parameters, profile):
        configured = self.configure_profile(
            motor_code, profile, parameters.get("stop_action")
        )
        if not configured.get("success"):
            return configured
        return self.motor_repository.execute_run_forever(
            motor_code, parameters.get("speed_sp")
        )

    def _run_direct(self, motor_code, parameters, profile):
        del profile
        configured = self.configure_profile(
            motor_code, self.direct_profile, parameters.get("stop_action")
        )
        if not configured.get("success"):
            return configured
        return self.motor_repository.execute_run_direct(
            motor_code, parameters.get("duty_cycle_sp")
        )

    def _run_to_rel_pos(self, motor_code, parameters, profile):
        configured = self.configure_profile(
            motor_code, profile, parameters.get("stop_action")
        )
        if not configured.get("success"):
            return configured
        return self.motor_repository.execute_run_to_rel_pos(
            motor_code,
            parameters.get("speed_sp"),
            parameters.get("position_sp")
        )

    def _run_to_abs_pos(self, motor_code, parameters, profile):
        configured = self.configure_profile(
            motor_code, profile, parameters.get("stop_action")
        )
        if not configured.get("success"):
            return configured
        return self.motor_repository.execute_run_to_abs_pos(
            motor_code,
            parameters.get("speed_sp"),
            parameters.get("position_sp")
        )

    def _reset(self, motor_code, parameters, profile):
        del parameters
        del profile
        return self.motor_repository.execute_reset(motor_code)

    def configure_profile(self, motor_code, profile, stop_action=None):
        stop_action = stop_action or self.default_stop_action
        ramp_up = (
            self.ramp_up_ms
            if profile in (self.ramp_up_profile, self.ramp_up_down_profile)
            else 0
        )
        ramp_down = (
            self.ramp_down_ms
            if profile in (self.ramp_down_profile, self.ramp_up_down_profile)
            else 0
        )
        return self.motor_repository.configure_motion(
            motor_code, stop_action, ramp_up, ramp_down
        )
