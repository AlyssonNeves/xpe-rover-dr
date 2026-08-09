#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Differential-drive odometry, gyro state and basic navigation service."""

import copy
import math
import threading
import time

from app.rover_config import (
    DRIVE_CONFIG,
    DRIVE_GYRO_SENSOR_CODE,
    DRIVE_LEFT_MOTOR_CODE,
    DRIVE_RIGHT_MOTOR_CODE,
    DRIVE_TRACK_WIDTH_MM,
    DRIVE_WHEEL_DIAMETER_MM,
    MOTOR_DEFAULT_STOP_ACTION,
    MOTOR_RUN_FOREVER_WATCHDOG_MS,
)


class DriveService(object):
    """Coordinates traction motors above MotorPort without direct EV3 access."""

    def __init__(self, motor_port, sensor_port=None, config=None):
        self.motor_port = motor_port
        self.sensor_port = sensor_port
        self.config = copy.deepcopy(config or DRIVE_CONFIG)
        self.left_motor_code = self.config.get(
            "left_motor_code", DRIVE_LEFT_MOTOR_CODE
        )
        self.right_motor_code = self.config.get(
            "right_motor_code", DRIVE_RIGHT_MOTOR_CODE
        )
        self.gyro_sensor_code = self.config.get(
            "gyro_sensor_code", DRIVE_GYRO_SENSOR_CODE
        )
        self.wheel_diameter_mm = float(
            self.config.get("wheel_diameter_mm", DRIVE_WHEEL_DIAMETER_MM)
        )
        self.track_width_mm = float(
            self.config.get("track_width_mm", DRIVE_TRACK_WIDTH_MM)
        )
        self.left_speed_factor = float(
            self.config.get("left_speed_factor", 1.0)
        )
        self.right_speed_factor = float(
            self.config.get("right_speed_factor", 1.0)
        )
        self._lock = threading.RLock()
        self._last_drive_command = None
        self._last_encoder = None
        self._pose = {
            "x_mm": 0.0,
            "y_mm": 0.0,
            "heading_deg": 0.0,
            "distance_mm": 0.0,
        }

    def get_status(self):
        """Returns current traction state, gyro reading and estimated pose."""
        self._update_odometry()
        with self._lock:
            pose = copy.deepcopy(self._pose)
            last_command = copy.deepcopy(self._last_drive_command)

        return {
            "mode": "differential",
            "left_motor_code": self.left_motor_code,
            "right_motor_code": self.right_motor_code,
            "gyro_sensor_code": self.gyro_sensor_code,
            "gyro_angle_deg": self._read_gyro_angle(),
            "pose": pose,
            "calibration": {
                "wheel_diameter_mm": self.wheel_diameter_mm,
                "track_width_mm": self.track_width_mm,
                "left_speed_factor": self.left_speed_factor,
                "right_speed_factor": self.right_speed_factor,
            },
            "left_motor": self.motor_port.read_motor(self.left_motor_code),
            "right_motor": self.motor_port.read_motor(self.right_motor_code),
            "last_drive_command": last_command,
        }

    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        """Resets pose and captures the current encoder positions as baseline."""
        with self._lock:
            self._pose = {
                "x_mm": float(x_mm),
                "y_mm": float(y_mm),
                "heading_deg": self._normalize_angle(float(heading_deg)),
                "distance_mm": 0.0,
            }
            self._last_encoder = self._read_encoder_positions()
            return copy.deepcopy(self._pose)

    def drive_tank(
        self, left_speed_sp, right_speed_sp, priority=None,
        stop_action=None, watchdog_ms=None
    ):
        """Submits a synchronized continuous command for both traction motors."""
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION
        watchdog_ms = (
            MOTOR_RUN_FOREVER_WATCHDOG_MS
            if watchdog_ms is None
            else watchdog_ms
        )
        priority = 0 if priority is None else priority

        if left_speed_sp == 0 and right_speed_sp == 0:
            return self.stop(stop_action)

        commands = [
            self._continuous_command(
                self.left_motor_code, left_speed_sp, priority,
                stop_action, watchdog_ms, self.left_speed_factor
            ),
            self._continuous_command(
                self.right_motor_code, right_speed_sp, priority,
                stop_action, watchdog_ms, self.right_speed_factor
            ),
        ]
        result = self.motor_port.run_synchronized_motors(commands)
        self._remember_command("tank", result, {
            "left_speed_sp": left_speed_sp,
            "right_speed_sp": right_speed_sp,
            "priority": priority,
            "stop_action": stop_action,
            "watchdog_ms": watchdog_ms,
        })
        return result

    def move_distance(
        self, distance_mm, speed_sp, priority=None, stop_action=None,
        timeout_ms=None
    ):
        """Queues equal wheel displacements for straight-line motion."""
        wheel_degrees = self._millimeters_to_degrees(distance_mm)
        result = self._queue_relative_motion(
            wheel_degrees,
            wheel_degrees,
            speed_sp,
            speed_sp,
            priority,
            stop_action,
            timeout_ms,
        )
        self._remember_command("move-distance", result, {
            "distance_mm": float(distance_mm),
            "speed_sp": int(speed_sp),
        })
        return self._decorate_navigation_result(
            result, "move-distance", distance_mm=float(distance_mm)
        )

    def rotate_angle(
        self, angle_deg, speed_sp, priority=None, stop_action=None,
        timeout_ms=None
    ):
        """Queues opposite wheel displacements for an in-place rotation."""
        arc_mm = math.pi * self.track_width_mm * float(angle_deg) / 360.0
        left_degrees = -self._millimeters_to_degrees(arc_mm)
        right_degrees = self._millimeters_to_degrees(arc_mm)
        result = self._queue_relative_motion(
            left_degrees,
            right_degrees,
            speed_sp,
            speed_sp,
            priority,
            stop_action,
            timeout_ms,
        )
        self._remember_command("rotate-angle", result, {
            "angle_deg": float(angle_deg),
            "speed_sp": int(speed_sp),
        })
        return self._decorate_navigation_result(
            result, "rotate-angle", angle_deg=float(angle_deg)
        )

    def curve_radius(
        self, radius_mm, angle_deg, speed_sp, priority=None,
        stop_action=None, timeout_ms=None
    ):
        """Queues an arc by calculating independent left/right wheel travel."""
        radius_mm = float(radius_mm)
        angle_deg = float(angle_deg)
        half_track = self.track_width_mm / 2.0
        if abs(radius_mm) <= half_track:
            raise ValueError(
                "radius_mm must be greater than half the track width"
            )

        signed_angle_rad = math.radians(angle_deg)
        left_radius = radius_mm - half_track
        right_radius = radius_mm + half_track
        left_mm = left_radius * signed_angle_rad
        right_mm = right_radius * signed_angle_rad

        max_distance = max(abs(left_mm), abs(right_mm))
        left_speed = max(1, int(abs(speed_sp) * abs(left_mm) / max_distance))
        right_speed = max(1, int(abs(speed_sp) * abs(right_mm) / max_distance))

        result = self._queue_relative_motion(
            self._millimeters_to_degrees(left_mm),
            self._millimeters_to_degrees(right_mm),
            left_speed,
            right_speed,
            priority,
            stop_action,
            timeout_ms,
        )
        self._remember_command("curve-radius", result, {
            "radius_mm": radius_mm,
            "angle_deg": angle_deg,
            "speed_sp": int(speed_sp),
        })
        return self._decorate_navigation_result(
            result,
            "curve-radius",
            radius_mm=radius_mm,
            angle_deg=angle_deg,
        )

    def stop(self, stop_action=None):
        """Stops both traction motors using the existing preemptive stop path."""
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION
        left = self.motor_port.stop_motor(self.left_motor_code, stop_action)
        right = self.motor_port.stop_motor(self.right_motor_code, stop_action)
        accepted = bool(
            left and right and left.get("accepted") and right.get("accepted")
        )
        result = {
            "accepted": accepted,
            "action": "stop",
            "stop_action": stop_action,
            "motors": {
                self.left_motor_code: left,
                self.right_motor_code: right,
            },
        }
        if not accepted:
            result["error"] = "One or more traction motors could not be stopped"
        self._remember_command("stop", result, {"stop_action": stop_action})
        return result

    def _queue_relative_motion(
        self, left_degrees, right_degrees, left_speed, right_speed,
        priority, stop_action, timeout_ms
    ):
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION
        priority = 0 if priority is None else priority
        commands = [
            self._relative_command(
                self.left_motor_code, left_speed, left_degrees, priority,
                stop_action, timeout_ms, self.left_speed_factor
            ),
            self._relative_command(
                self.right_motor_code, right_speed, right_degrees, priority,
                stop_action, timeout_ms, self.right_speed_factor
            ),
        ]
        return self.motor_port.run_synchronized_motors(commands)

    @staticmethod
    def _continuous_command(
        code, speed, priority, stop_action, watchdog_ms, factor
    ):
        return {
            "code": code,
            "action": "run-forever",
            "priority": priority,
            "parameters": {
                "speed_sp": int(round(speed * factor)),
                "stop_action": stop_action,
                "watchdog_ms": watchdog_ms,
            },
        }

    @staticmethod
    def _relative_command(
        code, speed, degrees, priority, stop_action, timeout_ms, factor
    ):
        return {
            "code": code,
            "action": "run-to-rel-pos",
            "priority": priority,
            "parameters": {
                "speed_sp": max(1, int(round(abs(speed) * factor))),
                "position_sp": int(round(degrees)),
                "stop_action": stop_action,
                "timeout_ms": timeout_ms,
            },
        }

    @staticmethod
    def _decorate_navigation_result(result, navigation_action, **target):
        decorated = dict(result or {})
        decorated["navigation_action"] = navigation_action
        decorated["target"] = target
        return decorated

    def _remember_command(self, action, result, parameters):
        with self._lock:
            self._last_drive_command = {
                "action": action,
                "parameters": copy.deepcopy(parameters),
                "submitted_at": time.time(),
                "accepted": bool(result and result.get("accepted")),
                "batch_id": result.get("batch_id") if result else None,
            }

    def _update_odometry(self):
        current = self._read_encoder_positions()
        with self._lock:
            if self._last_encoder is None:
                self._last_encoder = current
                gyro = self._read_gyro_angle()
                if gyro is not None:
                    self._pose["heading_deg"] = self._normalize_angle(gyro)
                return

            delta_left_deg = current[0] - self._last_encoder[0]
            delta_right_deg = current[1] - self._last_encoder[1]
            self._last_encoder = current

            delta_left_mm = self._degrees_to_millimeters(delta_left_deg)
            delta_right_mm = self._degrees_to_millimeters(delta_right_deg)
            delta_center_mm = (delta_left_mm + delta_right_mm) / 2.0
            delta_heading_rad = (
                (delta_right_mm - delta_left_mm) / self.track_width_mm
            )

            heading_before = math.radians(self._pose["heading_deg"])
            heading_mid = heading_before + delta_heading_rad / 2.0
            self._pose["x_mm"] += delta_center_mm * math.cos(heading_mid)
            self._pose["y_mm"] += delta_center_mm * math.sin(heading_mid)
            self._pose["distance_mm"] += abs(delta_center_mm)

            gyro = self._read_gyro_angle()
            if gyro is not None:
                self._pose["heading_deg"] = self._normalize_angle(gyro)
            else:
                self._pose["heading_deg"] = self._normalize_angle(
                    self._pose["heading_deg"] + math.degrees(delta_heading_rad)
                )

    def _read_encoder_positions(self):
        left = self.motor_port.read_motor(self.left_motor_code) or {}
        right = self.motor_port.read_motor(self.right_motor_code) or {}
        try:
            return float(left.get("position", 0.0)), float(
                right.get("position", 0.0)
            )
        except (TypeError, ValueError):
            return 0.0, 0.0

    def _read_gyro_angle(self):
        if self.sensor_port is None:
            return None
        sensor = self.sensor_port.read_sensor(self.gyro_sensor_code)
        if not sensor:
            return None
        value = sensor.get("value")
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _degrees_to_millimeters(self, degrees):
        return float(degrees) / 360.0 * math.pi * self.wheel_diameter_mm

    def _millimeters_to_degrees(self, millimeters):
        return int(round(
            float(millimeters) / (math.pi * self.wheel_diameter_mm) * 360.0
        ))

    @staticmethod
    def _normalize_angle(angle):
        return (float(angle) + 180.0) % 360.0 - 180.0
