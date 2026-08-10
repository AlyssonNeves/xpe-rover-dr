#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-level motor command execution and EV3 movement-profile mapping."""


class MotorCommandExecutor(object):
    """Applies one movement profile and issues an already validated command."""

    def __init__(self, motor_repository, actions, default_stop_action,
                 ramp_up_ms, ramp_down_ms, direct_profile, ramp_up_profile,
                 ramp_down_profile, ramp_up_down_profile):
        self.motor_repository = motor_repository
        self.actions = actions
        self.default_stop_action = default_stop_action
        self.ramp_up_ms = int(ramp_up_ms)
        self.ramp_down_ms = int(ramp_down_ms)
        self.direct_profile = direct_profile
        self.ramp_up_profile = ramp_up_profile
        self.ramp_down_profile = ramp_down_profile
        self.ramp_up_down_profile = ramp_up_down_profile

    def configure_profile(self, motor_code, profile, stop_action=None):
        """Maps a logical profile to native EV3 ramp-up/ramp-down settings."""
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

    def execute(self, motor_code, action, parameters):
        """Configures the profile and starts one native motor operation."""
        params = dict(parameters or {})
        stop_action = params.get("stop_action") or self.default_stop_action

        if action == self.actions.STOP:
            return self.motor_repository.stop_motor(motor_code, stop_action)
        if action == self.actions.RESET:
            return self.motor_repository.reset_motor(motor_code)

        profile = params.get("profile") or self.direct_profile
        configured, error = self.configure_profile(
            motor_code, profile, stop_action
        )
        if not configured:
            return False, error

        if action == self.actions.RUN_TIMED:
            return self.motor_repository.run_timed_motor(
                motor_code, params["speed_sp"], params["time_sp"], stop_action
            )
        if action == self.actions.RUN_FOREVER:
            return self.motor_repository.run_forever_motor(
                motor_code, params["speed_sp"], stop_action
            )
        if action == self.actions.RUN_TO_REL_POS:
            return self.motor_repository.run_to_rel_pos_motor(
                motor_code, params["speed_sp"], params["position_sp"],
                stop_action
            )
        return False, "Unsupported queued motor action"
