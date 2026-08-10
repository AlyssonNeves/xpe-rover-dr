#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""High-level differential-drive navigation service for Rover DR."""

import math
import threading
import time

from ports.drive_port import DrivePort


class DriveCommandStates(object):
    """Defines navigation command lifecycle states."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    STALLED = "STALLED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"


class DriveService(DrivePort):
    """
    Coordinates traction motors, gyro feedback, odometry and trajectory telemetry.

    The service operates above the motor port and therefore preserves the
    application's hexagonal separation from the EV3 hardware driver.
    """

    def __init__(self, motor_query_port, drive_motor_port, motor_command_port,
                 motor_command_query_port, sensor_port, config,
                 clock=None, sleeper=None):
        if config is None:
            raise ValueError("Resolved drive configuration is required.")
        self.motor_query_port = motor_query_port
        self.drive_motor_port = drive_motor_port
        self.motor_command_port = motor_command_port
        self.motor_command_query_port = motor_command_query_port
        self.sensor_port = sensor_port
        self.config = dict(config)
        self.clock = clock or time.time
        self.sleeper = sleeper or time.sleep
        self.left_motor_code = self.config["left_motor_code"]
        self.right_motor_code = self.config["right_motor_code"]
        self.gyro_sensor_code = self.config["gyro_sensor_code"]
        self.wheel_diameter_mm = float(self.config["wheel_diameter_mm"])
        self.track_width_mm = float(self.config["track_width_mm"])
        self.left_speed_factor = float(self.config["left_speed_factor"])
        self.right_speed_factor = float(self.config["right_speed_factor"])
        self.heading_kp = float(self.config["heading_kp"])
        self.control_interval_seconds = (
            float(self.config["control_interval_ms"]) / 1000.0
        )
        self.distance_tolerance_mm = float(
            self.config["distance_tolerance_mm"]
        )
        self.angle_tolerance_deg = float(self.config["angle_tolerance_deg"])
        self.stall_timeout_seconds = (
            float(self.config["stall_timeout_ms"]) / 1000.0
        )
        self.max_recovery_attempts = int(self.config["max_recovery_attempts"])
        self.recovery_distance_mm = float(self.config["recovery_distance_mm"])
        self.telemetry_limit = int(self.config["telemetry_limit"])
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker = None
        self._command_sequence = 0
        self._active_command = None
        self._telemetry = []
        self._pose = {"x_mm": 0.0, "y_mm": 0.0, "heading_deg": 0.0, "distance_mm": 0.0}
        self._last_encoder = None
        self._last_error = None

    def get_status(self):
        """Returns the current navigation, pose and calibration state."""
        self._update_odometry()
        with self._lock:
            return {
                "state": self._active_command.get("state") if self._active_command else DriveCommandStates.IDLE,
                "active_command": dict(self._active_command) if self._active_command else None,
                "pose": dict(self._pose),
                "gyro_angle_deg": self._read_gyro_angle(),
                "calibration": {
                    "wheel_diameter_mm": self.wheel_diameter_mm,
                    "track_width_mm": self.track_width_mm,
                    "left_speed_factor": self.left_speed_factor,
                    "right_speed_factor": self.right_speed_factor,
                    "heading_kp": self.heading_kp
                },
                "last_error": self._last_error,
                "telemetry_samples": len(self._telemetry)
            }

    def get_telemetry(self, limit=None):
        """Returns recent trajectory telemetry samples."""
        with self._lock:
            samples = list(self._telemetry)
        if limit is not None:
            samples = samples[-max(0, int(limit)):]
        return samples

    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        """Resets the estimated rover pose and encoder baseline."""
        with self._lock:
            self._pose = {
                "x_mm": float(x_mm), "y_mm": float(y_mm),
                "heading_deg": float(heading_deg), "distance_mm": 0.0
            }
            self._last_encoder = self._read_encoder_positions()
            self._record_telemetry("odometry-reset")
            return dict(self._pose)

    def move_distance(self, distance_mm, speed_sp, **options):
        """Moves in a straight line while correcting heading with gyro feedback."""
        return self._start_command("move-distance", {
            "distance_mm": float(distance_mm), "speed_sp": abs(int(speed_sp)),
            "stop_action": options.get("stop_action"),
            "recover_on_stall": options.get("recover_on_stall", True)
        }, self._execute_move_distance)

    def rotate_angle(self, angle_deg, speed_sp, **options):
        """Rotates around the rover center using gyro feedback when available."""
        return self._start_command("rotate-angle", {
            "angle_deg": float(angle_deg), "speed_sp": abs(int(speed_sp)),
            "stop_action": options.get("stop_action"),
            "recover_on_stall": options.get("recover_on_stall", True)
        }, self._execute_rotate_angle)

    def curve_radius(self, radius_mm, angle_deg, speed_sp, **options):
        """Drives an arc with independently calculated wheel speeds."""
        if abs(float(radius_mm)) <= self.track_width_mm / 2.0:
            raise ValueError("radius_mm must be greater than half the track width")
        return self._start_command("curve-radius", {
            "radius_mm": float(radius_mm), "angle_deg": float(angle_deg),
            "speed_sp": abs(int(speed_sp)), "stop_action": options.get("stop_action"),
            "recover_on_stall": options.get("recover_on_stall", True)
        }, self._execute_curve_radius)

    def stop(self, stop_action=None):
        """Stops active navigation and both traction motors."""
        self._stop_event.set()
        result = self.drive_motor_port.stop_drive(stop_action)
        with self._lock:
            if self._active_command:
                self._active_command["state"] = DriveCommandStates.STOPPED
                self._active_command["finished_at"] = self.clock()
            self._record_telemetry("stop")
        return {"stopped": True, "motors": result, "status": self.get_status()}

    def _start_command(self, action, params, target):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return {"accepted": False, "error": "A navigation command is already running."}
            self._command_sequence += 1
            command = dict(params)
            command.update({
                "command_id": self._command_sequence, "action": action,
                "state": DriveCommandStates.RUNNING, "started_at": self.clock(),
                "recovery_attempts": 0
            })
            self._active_command = command
            self._last_error = None
            self._stop_event.clear()
            self._last_encoder = self._read_encoder_positions()
            self._record_telemetry("command-start")
            self._worker = threading.Thread(target=self._run_command, args=(target, command), name="DriveNavigationThread")
            self._worker.daemon = True
            self._worker.start()
            return {"accepted": True, "command": dict(command)}

    def _run_command(self, target, command):
        try:
            target(command)
            with self._lock:
                if command.get("state") == DriveCommandStates.RUNNING:
                    command["state"] = DriveCommandStates.COMPLETED
                command["finished_at"] = self.clock()
                self._record_telemetry("command-finish")
        except Exception as error:
            self.drive_motor_port.stop_drive(command.get("stop_action"))
            with self._lock:
                command["state"] = DriveCommandStates.FAILED
                command["finished_at"] = self.clock()
                command["error"] = str(error)
                self._last_error = str(error)
                self._record_telemetry("command-failed")

    def _execute_move_distance(self, command):
        target = command["distance_mm"]
        direction = 1 if target >= 0 else -1
        start_distance = self._pose["distance_mm"]
        target_heading = self._read_gyro_angle()
        if target_heading is None:
            target_heading = self._pose["heading_deg"]
        self._control_motion(command, abs(target), lambda: abs(self._pose["distance_mm"] - start_distance),
                             lambda: self._straight_speeds(direction * command["speed_sp"], target_heading))

    def _execute_rotate_angle(self, command):
        target_angle = command["angle_deg"]
        direction = 1 if target_angle >= 0 else -1
        start_heading = self._current_heading()
        self._control_motion(command, abs(target_angle), lambda: abs(self._angle_delta(self._current_heading(), start_heading)),
                             lambda: (-direction * command["speed_sp"], direction * command["speed_sp"]),
                             tolerance=self.angle_tolerance_deg)

    def _execute_curve_radius(self, command):
        radius = command["radius_mm"]
        angle = command["angle_deg"]
        direction = 1 if angle >= 0 else -1
        half_track = self.track_width_mm / 2.0
        outer = abs(radius) + half_track
        inner = abs(radius) - half_track
        base = command["speed_sp"]
        inner_speed = max(1, int(base * inner / outer))
        if radius > 0:
            speeds = (direction * base, direction * inner_speed)
        else:
            speeds = (direction * inner_speed, direction * base)
        start_heading = self._current_heading()
        self._control_motion(command, abs(angle), lambda: abs(self._angle_delta(self._current_heading(), start_heading)),
                             lambda: speeds, tolerance=self.angle_tolerance_deg)

    def _control_motion(self, command, target, progress_reader, speed_reader, tolerance=None):
        tolerance = self.distance_tolerance_mm if tolerance is None else tolerance
        last_progress = progress_reader()
        last_change = self.clock()
        while not self._stop_event.is_set():
            self._update_odometry()
            progress = progress_reader()
            if progress + tolerance >= target:
                break
            left_speed, right_speed = speed_reader()
            self.drive_motor_port.drive_tank(self._apply_left_factor(left_speed), self._apply_right_factor(right_speed), profile="navigation")
            self._record_telemetry("motion")
            if abs(progress - last_progress) >= max(0.5, tolerance * 0.1):
                last_progress = progress
                last_change = self.clock()
            elif self.clock() - last_change >= self.stall_timeout_seconds:
                if not command.get("recover_on_stall") or not self._recover_from_stall(command):
                    command["state"] = DriveCommandStates.STALLED
                    raise RuntimeError("Drive stalled before reaching the navigation target.")
                last_change = self.clock()
                last_progress = progress_reader()
            self.sleeper(self.control_interval_seconds)
        self.drive_motor_port.stop_drive(command.get("stop_action"))
        self._update_odometry()

    def _recover_from_stall(self, command):
        if command["recovery_attempts"] >= self.max_recovery_attempts:
            return False
        command["recovery_attempts"] += 1
        command["state"] = DriveCommandStates.RECOVERING
        self.drive_motor_port.stop_drive("brake")
        self._record_telemetry("stall-detected")
        recovery_degrees = self._millimeters_to_degrees(self.recovery_distance_mm)
        speed = max(50, int(command["speed_sp"] * 0.5))
        batch = self.motor_command_port.run_synchronized_motors([
            {"code": self.left_motor_code, "action": "run-to-rel-pos", "speed_sp": speed, "position_sp": -recovery_degrees},
            {"code": self.right_motor_code, "action": "run-to-rel-pos", "speed_sp": speed, "position_sp": -recovery_degrees}
        ])
        if not batch.get("success") or not self._wait_for_motor_commands(batch.get("command_ids", []), self.stall_timeout_seconds):
            self._record_telemetry("stall-recovery-failed")
            return False
        command["state"] = DriveCommandStates.RUNNING
        self._record_telemetry("stall-recovery")
        return True

    def _wait_for_motor_commands(self, command_ids, timeout_seconds):
        """Waits until all recovery commands reach successful terminal states."""
        if not command_ids:
            return True
        deadline = self.clock() + max(0.1, float(timeout_seconds))
        successful = ("COMPLETED",)
        failed = ("TIMED_OUT", "STALLED", "COMMAND_FAILED", "CANCELLED")
        while self.clock() < deadline:
            states = []
            for command_id in command_ids:
                snapshot = self.motor_command_query_port.get_command(command_id)
                states.append(snapshot.get("status") if snapshot else None)
            if states and all(state in successful for state in states):
                return True
            if any(state in failed for state in states):
                return False
            self.sleeper(self.control_interval_seconds)
        return False

    def _straight_speeds(self, base_speed, target_heading):
        current_heading = self._current_heading()
        error = self._angle_delta(target_heading, current_heading)
        correction = int(self.heading_kp * error)
        limit = max(1, int(abs(base_speed) * 0.35))
        correction = max(-limit, min(limit, correction))
        direction = 1 if base_speed >= 0 else -1
        return base_speed + direction * correction, base_speed - direction * correction

    def _apply_left_factor(self, speed):
        return int(speed * self.left_speed_factor)

    def _apply_right_factor(self, speed):
        return int(speed * self.right_speed_factor)

    def _read_encoder_positions(self):
        left = self.motor_query_port.read_motor(self.left_motor_code) or {}
        right = self.motor_query_port.read_motor(self.right_motor_code) or {}
        try:
            return float(left.get("position", 0.0)), float(right.get("position", 0.0))
        except (TypeError, ValueError):
            return 0.0, 0.0

    def _update_odometry(self):
        current = self._read_encoder_positions()
        with self._lock:
            if self._last_encoder is None:
                self._last_encoder = current
                return
            delta_left_deg = current[0] - self._last_encoder[0]
            delta_right_deg = current[1] - self._last_encoder[1]
            self._last_encoder = current
            delta_left = self._degrees_to_millimeters(delta_left_deg)
            delta_right = self._degrees_to_millimeters(delta_right_deg)
            delta_center = (delta_left + delta_right) / 2.0
            delta_heading_rad = (delta_right - delta_left) / self.track_width_mm
            heading_mid_rad = math.radians(self._pose["heading_deg"]) + delta_heading_rad / 2.0
            self._pose["x_mm"] += delta_center * math.cos(heading_mid_rad)
            self._pose["y_mm"] += delta_center * math.sin(heading_mid_rad)
            gyro = self._read_gyro_angle()
            self._pose["heading_deg"] = gyro if gyro is not None else self._normalize_angle(self._pose["heading_deg"] + math.degrees(delta_heading_rad))
            self._pose["distance_mm"] += abs(delta_center)

    def _read_gyro_angle(self):
        sensor = self.sensor_port.read_sensor(self.gyro_sensor_code)
        if not sensor:
            return None
        for key in ("value", "value0", "angle", "reading"):
            value = sensor.get(key)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        values = sensor.get("values")
        if isinstance(values, (list, tuple)) and values:
            try:
                return float(values[0])
            except (TypeError, ValueError):
                return None
        return None

    def _current_heading(self):
        gyro = self._read_gyro_angle()
        return gyro if gyro is not None else self._pose["heading_deg"]

    def _record_telemetry(self, event):
        sample = {
            "timestamp": self.clock(), "event": event,
            "command_id": self._active_command.get("command_id") if self._active_command else None,
            "command_state": self._active_command.get("state") if self._active_command else DriveCommandStates.IDLE,
            "pose": dict(self._pose), "gyro_angle_deg": self._read_gyro_angle(),
            "encoders": {"left": self._read_encoder_positions()[0], "right": self._read_encoder_positions()[1]}
        }
        self._telemetry.append(sample)
        if len(self._telemetry) > self.telemetry_limit:
            del self._telemetry[:-self.telemetry_limit]

    def _degrees_to_millimeters(self, degrees):
        return float(degrees) / 360.0 * math.pi * self.wheel_diameter_mm

    def _millimeters_to_degrees(self, millimeters):
        return int(round(float(millimeters) / (math.pi * self.wheel_diameter_mm) * 360.0))

    @staticmethod
    def _normalize_angle(angle):
        return (float(angle) + 180.0) % 360.0 - 180.0

    @classmethod
    def _angle_delta(cls, target, current):
        return cls._normalize_angle(float(target) - float(current))
