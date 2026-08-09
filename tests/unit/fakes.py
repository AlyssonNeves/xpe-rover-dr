from copy import deepcopy


class FakeSensorPort(object):
    def __init__(self):
        self.items = {
            "GYR": {"code": "GYR", "name": "Gyroscope", "value": 10.0, "connected": True},
            "TMP": {"code": "TMP", "name": "Temperature", "value": 22.0, "connected": True},
        }

    def list_sensors(self):
        return [{"code": k, "name": v["name"], "connected": v["connected"]}
                for k, v in sorted(self.items.items())]

    def read_sensor(self, code):
        value = self.items.get(code)
        return deepcopy(value) if value is not None else None

    def read_all_sensors(self):
        return [deepcopy(v) for _, v in sorted(self.items.items())]


class FakeMotorPort(object):
    def __init__(self):
        self.motors = {
            "LLM": {"code": "LLM", "address": "outA", "position": 0, "state": []},
            "RLM": {"code": "RLM", "address": "outD", "position": 0, "state": []},
        }
        self.commands = {}
        self.next_command_id = 1
        self.last_sync = None
        self.guard_calls = []

    def list_motors(self):
        return [{"code": k, "address": v["address"], "connected": True}
                for k, v in sorted(self.motors.items())]

    def read_motor(self, motor_code):
        value = self.motors.get(motor_code)
        return deepcopy(value) if value is not None else None

    def read_all_motors(self):
        return [deepcopy(v) for _, v in sorted(self.motors.items())]

    def _accepted(self, motor_code, action, status="QUEUED"):
        if motor_code not in self.motors:
            return None
        cid = self.next_command_id
        self.next_command_id += 1
        result = {
            "accepted": True,
            "status": status,
            "command_id": cid,
            "motor_code": motor_code,
            "action": action,
        }
        self.commands[cid] = deepcopy(result)
        return result

    def stop_motor(self, motor_code, stop_action=None):
        return self._accepted(motor_code, "stop", status="COMPLETED")

    def run_timed_motor(self, motor_code, speed_sp, time_sp, priority=None,
                        stop_action=None, timeout_ms=None):
        return self._accepted(motor_code, "run-timed")

    def run_forever_motor(self, motor_code, speed_sp, priority=None,
                          stop_action=None, watchdog_ms=None, timeout_ms=None):
        return self._accepted(motor_code, "run-forever")

    def run_to_rel_pos_motor(self, motor_code, speed_sp, position_sp,
                             priority=None, stop_action=None, timeout_ms=None):
        return self._accepted(motor_code, "run-to-rel-pos")

    def reset_motor(self, motor_code, priority=None):
        return self._accepted(motor_code, "reset")

    def get_command(self, command_id):
        return deepcopy(self.commands.get(command_id))

    def list_commands(self, motor_code=None):
        values = [deepcopy(v) for _, v in sorted(self.commands.items())]
        if motor_code is not None:
            values = [v for v in values if v.get("motor_code") == motor_code]
        return values

    def cancel_motor_commands(self, motor_code):
        if motor_code not in self.motors:
            return None
        return {"accepted": True, "motor_code": motor_code, "cancelled": 1}

    def run_synchronized_motors(self, commands):
        self.last_sync = deepcopy(commands)
        return {"accepted": True, "batch_id": "B-1", "commands": deepcopy(commands)}

    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        self.guard_calls.append((list(motor_codes), operation_name))
        return operation()

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        self.guard_calls.append((list(motor_codes), operation_name, operation_id))
        return {"operation_id": operation_id, "status": "RUNNING"}

    def end_guarded_operation(self, operation_id, status="COMPLETED",
                              error=None, stop=False):
        return {"operation_id": operation_id, "status": status, "stop": stop}


class FakeControllerPort(object):
    def read_controller_status(self):
        return {"status": "ok"}

    def read_network_status(self):
        return {"ip": "127.0.0.1"}

    def read_battery_status(self):
        return {"voltage": 7.4}

    def read_system_status(self):
        return {"platform": "test"}


class FakeRoverStatePort(object):
    def get_rover_state(self):
        return {"status": "consolidated"}


class FakeDrivePort(object):
    def __init__(self):
        self.calls = []

    def get_status(self):
        return {"mode": "differential"}

    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        self.calls.append(("reset", x_mm, y_mm, heading_deg))
        return {"x_mm": x_mm, "y_mm": y_mm, "heading_deg": heading_deg}

    def drive_tank(self, left_speed_sp, right_speed_sp, priority=None,
                   stop_action=None, watchdog_ms=None):
        self.calls.append(("tank", left_speed_sp, right_speed_sp))
        return {"accepted": True, "batch_id": "D-1"}

    def move_distance(self, distance_mm, speed_sp, priority=None,
                      stop_action=None, timeout_ms=None):
        return {"accepted": True, "batch_id": "D-2", "distance_mm": distance_mm}

    def rotate_angle(self, angle_deg, speed_sp, priority=None,
                     stop_action=None, timeout_ms=None):
        return {"accepted": True, "batch_id": "D-3", "angle_deg": angle_deg}

    def curve_radius(self, radius_mm, angle_deg, speed_sp, priority=None,
                     stop_action=None, timeout_ms=None):
        return {"accepted": True, "batch_id": "D-4", "radius_mm": radius_mm}

    def stop(self, stop_action=None):
        return {"accepted": True, "action": "stop"}
