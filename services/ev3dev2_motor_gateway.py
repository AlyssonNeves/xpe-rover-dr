#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Safety-managed EV3Dev2 motor-domain gateway.

Only LargeMotor, MediumMotor and the official EV3Dev2 movement helpers are
exposed. Every hardware operation is classified and executed through the Rover
motor safety boundary. Persistent operations retain their motor reservation
until physical completion, explicit stop, timeout, watchdog expiry or deletion.
"""

import inspect
import threading
import time
import uuid

from app import rover_config
from services.app_logger import AppLogger


class Ev3Dev2MotorGatewayError(Exception):
    """Raised when an EV3Dev2 operation violates the Rover domain policy."""


class OperationKinds(object):
    READ_ONLY = "READ_ONLY"
    IMMEDIATE_CONFIGURATION = "IMMEDIATE_CONFIGURATION"
    BOUNDED_BLOCKING = "BOUNDED_BLOCKING"
    BOUNDED_NON_BLOCKING = "BOUNDED_NON_BLOCKING"
    CONTINUOUS = "CONTINUOUS"
    BACKGROUND_SERVICE = "BACKGROUND_SERVICE"
    STOP = "STOP"


class Ev3Dev2MotorGateway(object):
    """Creates and operates EV3Dev2 objects supported by the Rover domain."""

    SUPPORTED_CLASSES = frozenset((
        "LargeMotor", "MediumMotor", "MotorSet", "MoveTank",
        "MoveSteering", "MoveJoystick", "MoveDifferential"
    ))
    MOTOR_CLASSES = frozenset(("LargeMotor", "MediumMotor"))
    MOVEMENT_CLASSES = frozenset((
        "MotorSet", "MoveTank", "MoveSteering", "MoveJoystick",
        "MoveDifferential"
    ))
    SPEED_CLASSES = frozenset((
        "SpeedInteger", "SpeedPercent", "SpeedRPS", "SpeedRPM",
        "SpeedDPS", "SpeedDPM"
    ))
    DANGEROUS_PROPERTIES = frozenset((
        "command", "duty_cycle_sp", "speed_sp", "position_sp", "time_sp"
    ))
    SAFE_WRITABLE_PROPERTIES = {
        "LargeMotor": frozenset((
            "polarity", "stop_action", "ramp_up_sp", "ramp_down_sp",
            "position", "speed_p", "speed_i", "speed_d",
            "position_p", "position_i", "position_d"
        )),
        "MediumMotor": frozenset((
            "polarity", "stop_action", "ramp_up_sp", "ramp_down_sp",
            "position", "speed_p", "speed_i", "speed_d",
            "position_p", "position_i", "position_d"
        ))
    }
    ALLOWED_METHODS = {
        "LargeMotor": frozenset((
            "on", "off", "stop", "reset", "run_forever", "run_direct",
            "run_timed", "run_to_rel_pos", "run_to_abs_pos", "on_for_seconds",
            "on_for_degrees", "on_for_rotations", "on_to_position", "wait",
            "wait_until", "wait_while", "wait_until_not_moving"
        )),
        "MediumMotor": frozenset((
            "on", "off", "stop", "reset", "run_forever", "run_direct",
            "run_timed", "run_to_rel_pos", "run_to_abs_pos", "on_for_seconds",
            "on_for_degrees", "on_for_rotations", "on_to_position", "wait",
            "wait_until", "wait_while", "wait_until_not_moving"
        )),
        "MotorSet": frozenset((
            "on", "off", "stop", "reset", "run_forever", "run_direct",
            "run_timed", "run_to_rel_pos", "run_to_abs_pos", "wait",
            "wait_until", "wait_while", "wait_until_not_moving", "set_args"
        )),
        "MoveTank": frozenset((
            "on", "off", "stop", "on_for_seconds", "on_for_degrees",
            "on_for_rotations", "follow_line", "follow_gyro_angle",
            "turn_degrees", "wait_until_not_moving"
        )),
        "MoveSteering": frozenset((
            "on", "off", "stop", "on_for_seconds", "on_for_degrees",
            "on_for_rotations", "wait_until_not_moving"
        )),
        "MoveJoystick": frozenset(("on", "off", "stop")),
        "MoveDifferential": frozenset((
            "on", "off", "stop", "on_for_distance", "on_arc_left",
            "on_arc_right", "turn_degrees", "turn_to_angle", "on_to_coordinates",
            "odometry_start", "odometry_stop", "odometry_coordinates_log",
            "wait_until_not_moving"
        ))
    }

    CONTINUOUS_METHODS = frozenset(("on", "run_forever", "run_direct"))
    BACKGROUND_METHODS = frozenset(("odometry_start",))
    STOP_METHODS = frozenset(("off", "stop", "odometry_stop"))
    WAIT_METHODS = frozenset(("wait", "wait_until", "wait_while", "wait_until_not_moving"))
    READ_ONLY_METHODS = frozenset((
        "get_speed_steering", "angle_to_speed_percentage", "odometry_coordinates_log"
    ))
    CONFIGURATION_METHODS = frozenset(("reset", "set_args"))

    def __init__(self, motor_port, drive_port=None, motor_module=None,
                 max_objects=None, object_ttl_seconds=None):
        if motor_port is None:
            raise Ev3Dev2MotorGatewayError("A MotorPort safety boundary is required.")
        if motor_module is None:
            try:
                import ev3dev2.motor as motor_module
            except ImportError as error:
                raise Ev3Dev2MotorGatewayError(
                    "ev3dev2.motor is not available: {}".format(error)
                )
        self.module = motor_module
        self.motor_port = motor_port
        self.drive_port = drive_port
        self.max_objects = max_objects or rover_config.MOTOR_GATEWAY_MAX_OBJECTS
        self.object_ttl_seconds = (
            object_ttl_seconds or rover_config.MOTOR_GATEWAY_OBJECT_TTL_SECONDS
        )
        self._objects = {}
        self._metadata = {}
        self._operations = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._lifecycle_thread = threading.Thread(
            target=self._lifecycle_loop, name="Ev3Dev2GatewayLifecycle"
        )
        self._lifecycle_thread.daemon = True
        self._lifecycle_thread.start()

    def catalog(self):
        classes = {}
        constants = {}
        for name in sorted(dir(self.module)):
            if name.startswith("_"):
                continue
            value = getattr(self.module, name)
            if name in self.SUPPORTED_CLASSES and inspect.isclass(value):
                properties = []
                for member_name in sorted(dir(value)):
                    if member_name.startswith("_"):
                        continue
                    descriptor = getattr(value, member_name, None)
                    if isinstance(descriptor, property):
                        properties.append({
                            "name": member_name,
                            "readable": descriptor.fget is not None,
                            "writable": member_name in self.SAFE_WRITABLE_PROPERTIES.get(name, ())
                        })
                classes[name] = {
                    "methods": sorted(self.ALLOWED_METHODS[name]),
                    "properties": properties,
                    "bases": [base.__name__ for base in value.__bases__]
                }
            elif name.isupper() or isinstance(value, (str, int, float, bool, type(None))):
                constants[name] = self._serialize(value)
        return {
            "module": self.module.__name__,
            "scope": "Complete LargeMotor and MediumMotor domain coverage with managed movement helpers",
            "operation_kinds": [
                OperationKinds.READ_ONLY, OperationKinds.IMMEDIATE_CONFIGURATION,
                OperationKinds.BOUNDED_BLOCKING, OperationKinds.BOUNDED_NON_BLOCKING,
                OperationKinds.CONTINUOUS, OperationKinds.BACKGROUND_SERVICE,
                OperationKinds.STOP
            ],
            "classes": classes,
            "constants": constants
        }

    def create(self, class_name, args=None, kwargs=None, object_id=None):
        self.cleanup_expired_objects()
        cls = self._supported_class(class_name)
        raw_args = args or []
        raw_kwargs = kwargs or {}
        resolved_args = self._resolve(raw_args)
        resolved_kwargs = self._resolve(raw_kwargs)
        with self._lock:
            if len(self._objects) >= self.max_objects:
                raise Ev3Dev2MotorGatewayError("Gateway object limit reached.")
        instance = cls(*resolved_args, **resolved_kwargs)
        motor_codes, addresses = self._resolve_motor_binding(
            class_name, raw_args, raw_kwargs, instance
        )
        object_id = object_id or uuid.uuid4().hex
        with self._lock:
            if object_id in self._objects:
                raise Ev3Dev2MotorGatewayError("Object id already exists: {}".format(object_id))
            self._objects[object_id] = instance
            self._metadata[object_id] = {
                "class": class_name,
                "motor_codes": motor_codes,
                "addresses": addresses,
                "created_at": time.time(),
                "last_used_at": time.time()
            }
        return self.describe(object_id)

    def list_objects(self):
        self.cleanup_expired_objects()
        with self._lock:
            ids = sorted(self._objects.keys())
        return [self.describe(object_id) for object_id in ids]

    def list_operations(self):
        """Returns deterministic snapshots of gateway-managed operations."""
        with self._lock:
            operations = sorted(
                self._operations.values(),
                key=lambda item: (item.get("created_at", 0), item.get("operation_id", ""))
            )
            return [self._operation_view(item) for item in operations]

    def describe(self, object_id):
        obj = self._get(object_id)
        metadata = self._metadata[object_id]
        return {
            "object_id": object_id,
            "class": obj.__class__.__name__,
            "motor_codes": list(metadata["motor_codes"]),
            "addresses": list(metadata["addresses"]),
            "active_operations": [
                self._operation_view(item) for item in self._object_operations(object_id)
            ],
            "safety_managed": True
        }

    def delete(self, object_id):
        obj = self._get(object_id)
        metadata = self._metadata[object_id]
        self._stop_object(object_id, obj, metadata, "DELETED")
        with self._lock:
            self._objects.pop(object_id, None)
            self._metadata.pop(object_id, None)
        return {"object_id": object_id, "deleted": True, "hardware_stopped": True}

    def invoke(self, object_id, method_name, args=None, kwargs=None):
        obj = self._get(object_id)
        metadata = self._metadata[object_id]
        self._validate_method(metadata["class"], method_name)
        raw_kwargs = dict(kwargs or {})
        kind = self._classify(method_name, raw_kwargs)
        timeout_ms = self._extract_timeout(method_name, raw_kwargs, kind)
        watchdog_ms = self._extract_watchdog(raw_kwargs, kind)
        self._apply_dynamic_limits(metadata, method_name, args or [], raw_kwargs)
        resolved_args = self._resolve(args or [])
        resolved_kwargs = self._resolve(raw_kwargs)
        method = getattr(obj, method_name, None)
        if method is None or not callable(method):
            raise Ev3Dev2MotorGatewayError("Unknown public method: {}".format(method_name))
        self._touch(object_id)

        if kind == OperationKinds.READ_ONLY:
            result = method(*resolved_args, **resolved_kwargs)
            return self._invoke_result(object_id, method_name, kind, result, None)

        if kind == OperationKinds.STOP:
            result = method(*resolved_args, **resolved_kwargs)
            self._finish_object_operations(object_id, "STOPPED", stop=False)
            return self._invoke_result(object_id, method_name, kind, result, None)

        if kind in (OperationKinds.IMMEDIATE_CONFIGURATION, OperationKinds.BOUNDED_BLOCKING):
            def call():
                return method(*resolved_args, **resolved_kwargs)
            result = self.motor_port.execute_guarded_operation(
                metadata["motor_codes"], "{}.{}".format(metadata["class"], method_name), call
            )
            return self._invoke_result(object_id, method_name, kind, result, None)

        operation_id = uuid.uuid4().hex
        self.motor_port.begin_guarded_operation(
            metadata["motor_codes"], "{}.{}".format(metadata["class"], method_name), operation_id
        )
        now = time.time()
        operation = {
            "operation_id": operation_id,
            "object_id": object_id,
            "class": metadata["class"],
            "method": method_name,
            "kind": kind,
            "motor_codes": list(metadata["motor_codes"]),
            "started_at": now,
            "deadline": now + (float(timeout_ms) / 1000.0) if timeout_ms else None,
            "watchdog_deadline": now + (float(watchdog_ms) / 1000.0) if watchdog_ms else None,
            "status": "RUNNING"
        }
        with self._lock:
            self._operations[operation_id] = operation
        try:
            result = method(*resolved_args, **resolved_kwargs)
        except Exception as error:
            self._finish_operation(operation_id, "FAILED", error=error, stop=True)
            raise
        return self._invoke_result(object_id, method_name, kind, result, operation_id)

    def get_property(self, object_id, property_name):
        obj = self._get(object_id)
        self._validate_public_name(property_name)
        if not hasattr(obj, property_name):
            raise Ev3Dev2MotorGatewayError("Unknown public property: {}".format(property_name))
        self._touch(object_id)
        return {
            "object_id": object_id,
            "property": property_name,
            "value": self._serialize(getattr(obj, property_name))
        }

    def set_property(self, object_id, property_name, value):
        obj = self._get(object_id)
        metadata = self._metadata[object_id]
        self._validate_public_name(property_name)
        if property_name in self.DANGEROUS_PROPERTIES:
            raise Ev3Dev2MotorGatewayError(
                "Direct write is forbidden for dangerous property: {}".format(property_name)
            )
        if property_name not in self.SAFE_WRITABLE_PROPERTIES.get(metadata["class"], ()):
            raise Ev3Dev2MotorGatewayError("Property is not allowed by class policy: {}".format(property_name))
        descriptor = getattr(type(obj), property_name, None)
        if not isinstance(descriptor, property) or descriptor.fset is None:
            raise Ev3Dev2MotorGatewayError("Property is not writable: {}".format(property_name))
        resolved_value = self._resolve(value)
        self._validate_property_value(obj, property_name, resolved_value)

        def write():
            setattr(obj, property_name, resolved_value)
            return getattr(obj, property_name)

        result = self.motor_port.execute_guarded_operation(
            metadata["motor_codes"], "{}.{}=".format(metadata["class"], property_name), write
        )
        self._touch(object_id)
        return {"object_id": object_id, "property": property_name, "value": self._serialize(result)}

    def module_value(self, name):
        self._validate_public_name(name)
        if not hasattr(self.module, name):
            raise Ev3Dev2MotorGatewayError("Unknown module member: {}".format(name))
        value = getattr(self.module, name)
        if inspect.isclass(value) and name not in self.SUPPORTED_CLASSES and name not in self.SPEED_CLASSES:
            raise Ev3Dev2MotorGatewayError("Class is outside the Rover motor scope: {}".format(name))
        return {"name": name, "value": self._serialize(value)}

    def cleanup_expired_objects(self):
        cutoff = time.time() - self.object_ttl_seconds
        with self._lock:
            expired = [
                object_id for object_id, metadata in self._metadata.items()
                if metadata.get("last_used_at", metadata["created_at"]) < cutoff
                and not self._object_operations(object_id)
            ]
        for object_id in expired:
            try:
                self.delete(object_id)
            except Exception as error:
                AppLogger.error(
                    "Failed to delete expired EV3Dev2 object {}: {}".format(
                        object_id,
                        error
                    )
                )
        return len(expired)

    def close(self):
        self._stop_event.set()
        with self._lock:
            ids = list(self._objects.keys())
        for object_id in ids:
            try:
                self.delete(object_id)
            except Exception as error:
                AppLogger.error(
                    "Failed to safely delete EV3Dev2 object {} during shutdown: {}".format(
                        object_id,
                        error
                    )
                )
        self._lifecycle_thread.join(1.0)
        if self._lifecycle_thread.is_alive():
            AppLogger.error("EV3Dev2 gateway lifecycle thread did not stop.")

    def _lifecycle_loop(self):
        while not self._stop_event.wait(0.1):
            now = time.time()
            with self._lock:
                operations = list(self._operations.values())
            for operation in operations:
                if operation.get("watchdog_deadline") and now >= operation["watchdog_deadline"]:
                    self._finish_operation(operation["operation_id"], "WATCHDOG_EXPIRED", stop=True)
                    continue
                if operation.get("deadline") and now >= operation["deadline"]:
                    self._finish_operation(operation["operation_id"], "TIMED_OUT", stop=True)
                    continue
                if operation["kind"] == OperationKinds.BOUNDED_NON_BLOCKING and self._motors_idle(operation["motor_codes"]):
                    self._finish_operation(operation["operation_id"], "COMPLETED", stop=False)
            self.cleanup_expired_objects()

    def _motors_idle(self, motor_codes):
        for code in motor_codes:
            try:
                state = self.motor_port.read_motor(code) or {}
                states = state.get("state") or state.get("states") or []
                if isinstance(states, str):
                    states = states.split()
                if "running" in states or "ramping" in states:
                    return False
            except Exception as error:
                AppLogger.warning(
                    "Unable to determine whether motor {} is idle: {}".format(
                        code,
                        error
                    )
                )
                return False
        return True

    def _finish_operation(self, operation_id, status, error=None, stop=False):
        with self._lock:
            operation = self._operations.pop(operation_id, None)
        if operation is None:
            return None
        try:
            self.motor_port.end_guarded_operation(
                operation_id, status=status, error=error, stop=stop
            )
        finally:
            operation["status"] = status
            operation["finished_at"] = time.time()
            if error is not None:
                operation["error"] = str(error)
        return operation

    def _finish_object_operations(self, object_id, status, stop):
        for operation in self._object_operations(object_id):
            self._finish_operation(operation["operation_id"], status, stop=stop)

    def _stop_object(self, object_id, obj, metadata, status):
        try:
            if metadata["class"] == "MoveDifferential":
                odometry_stop = getattr(obj, "odometry_stop", None)
                if callable(odometry_stop):
                    odometry_stop()
            stop_method = getattr(obj, "off", None) or getattr(obj, "stop", None)
            if callable(stop_method):
                stop_method()
        finally:
            self._finish_object_operations(object_id, status, stop=True)

    def _resolve_motor_binding(self, class_name, args, kwargs, instance):
        configured = self.motor_port.list_motors()
        address_to_code = {}
        for item in configured:
            address = item.get("address")
            code = item.get("code")
            if address and code:
                address_to_code[address] = code
        addresses = []
        if class_name in self.MOTOR_CLASSES:
            address = kwargs.get("address") if "address" in kwargs else (
                args[0] if args else getattr(instance, "address", None)
            )
            addresses = [address]
        elif class_name == "MotorSet":
            specs = kwargs.get("motor_specs") if "motor_specs" in kwargs else (
                args[0] if args else getattr(instance, "motor_specs", None)
            )
            if not isinstance(specs, dict) or not specs:
                raise Ev3Dev2MotorGatewayError("MotorSet.motor_specs must be a non-empty dictionary.")
            addresses = list(specs.keys())
        else:
            candidates = list(args[:2]) + [kwargs.get("left_motor_port"), kwargs.get("right_motor_port")]
            addresses = [value for value in candidates if isinstance(value, str)]
            if len(addresses) != 2:
                ports = getattr(instance, "ports", None)
                if isinstance(ports, (list, tuple)):
                    addresses = list(ports)
        if not addresses or any(address not in address_to_code for address in addresses):
            unknown = [address for address in addresses if address not in address_to_code]
            raise Ev3Dev2MotorGatewayError(
                "Object contains unknown or unconfigured motor ports: {}".format(unknown or addresses)
            )
        actual_addresses = self._extract_actual_addresses(class_name, instance, addresses)
        if sorted(actual_addresses) != sorted(addresses):
            raise Ev3Dev2MotorGatewayError(
                "The object's real port set does not exactly match the validated port set."
            )
        codes = []
        for address in addresses:
            code = address_to_code[address]
            if code not in codes:
                codes.append(code)
        return codes, addresses

    def _extract_actual_addresses(self, class_name, instance, fallback):
        if class_name in self.MOTOR_CLASSES:
            return [getattr(instance, "address", None)]
        if class_name == "MotorSet":
            specs = getattr(instance, "motor_specs", None)
            if isinstance(specs, dict):
                return list(specs.keys())
            motors = getattr(instance, "motors", None)
            if isinstance(motors, dict):
                result = []
                for motor in motors.values():
                    address = getattr(motor, "address", None)
                    if address:
                        result.append(address)
                if result:
                    return result
        ports = getattr(instance, "ports", None)
        if isinstance(ports, (list, tuple)):
            return list(ports)
        left = getattr(instance, "left_motor", None)
        right = getattr(instance, "right_motor", None)
        values = [getattr(left, "address", None), getattr(right, "address", None)]
        values = [item for item in values if item]
        return values or list(fallback)

    def _classify(self, method_name, kwargs):
        if method_name in self.READ_ONLY_METHODS:
            return OperationKinds.READ_ONLY
        if method_name in self.STOP_METHODS:
            return OperationKinds.STOP
        if method_name in self.CONFIGURATION_METHODS:
            return OperationKinds.IMMEDIATE_CONFIGURATION
        if method_name in self.BACKGROUND_METHODS:
            return OperationKinds.BACKGROUND_SERVICE
        if method_name in self.CONTINUOUS_METHODS:
            return OperationKinds.CONTINUOUS
        if method_name in self.WAIT_METHODS:
            return OperationKinds.BOUNDED_BLOCKING
        if kwargs.get("block") is False:
            return OperationKinds.BOUNDED_NON_BLOCKING
        return OperationKinds.BOUNDED_BLOCKING

    def _extract_timeout(self, method_name, kwargs, kind):
        timeout_ms = kwargs.pop("rover_timeout_ms", None)
        if method_name in self.WAIT_METHODS and timeout_ms is None:
            raise Ev3Dev2MotorGatewayError("wait* methods require rover_timeout_ms.")
        if timeout_ms is not None:
            timeout_ms = int(timeout_ms)
            if timeout_ms <= 0 or timeout_ms > rover_config.MOTOR_GATEWAY_WAIT_MAX_TIMEOUT_MS:
                raise Ev3Dev2MotorGatewayError("Invalid rover_timeout_ms.")
        if kind == OperationKinds.BOUNDED_NON_BLOCKING and timeout_ms is None:
            raise Ev3Dev2MotorGatewayError("Non-blocking operations require rover_timeout_ms.")
        return timeout_ms

    def _extract_watchdog(self, kwargs, kind):
        watchdog_ms = kwargs.pop("rover_watchdog_ms", None)
        if kind == OperationKinds.CONTINUOUS:
            if watchdog_ms is None:
                raise Ev3Dev2MotorGatewayError("Continuous operations require rover_watchdog_ms.")
            watchdog_ms = int(watchdog_ms)
            if watchdog_ms <= 0 or watchdog_ms > rover_config.MOTOR_GATEWAY_MAX_WATCHDOG_MS:
                raise Ev3Dev2MotorGatewayError("Invalid rover_watchdog_ms.")
        elif watchdog_ms is not None:
            raise Ev3Dev2MotorGatewayError("rover_watchdog_ms is valid only for continuous operations.")
        return watchdog_ms

    def _apply_dynamic_limits(self, metadata, method_name, args, kwargs):
        max_speeds = []
        for code in metadata["motor_codes"]:
            motor = self.motor_port.read_motor(code) or {}
            value = motor.get("max_speed")
            if value is not None:
                max_speeds.append(abs(float(value)))
        max_speed = min(max_speeds) if max_speeds else None
        speed_keys = ("speed", "left_speed", "right_speed", "speed_sp")
        for key in speed_keys:
            if key in kwargs:
                self._validate_speed(kwargs[key], max_speed)
        if method_name in ("run_forever", "run_timed", "run_to_rel_pos", "run_to_abs_pos") and args:
            self._validate_speed(args[0], max_speed)
        if method_name == "run_direct":
            duty = kwargs.get("duty_cycle_sp", args[0] if args else None)
            if duty is not None and abs(float(duty)) > 100:
                raise Ev3Dev2MotorGatewayError("duty_cycle_sp must be between -100 and 100.")

    def _validate_speed(self, value, max_speed):
        if isinstance(value, dict) and "$speed" in value:
            if value["$speed"] not in self.SPEED_CLASSES:
                raise Ev3Dev2MotorGatewayError("Unsupported speed class.")
            numeric = float(value.get("value"))
            if value["$speed"] == "SpeedPercent" and abs(numeric) > 100:
                raise Ev3Dev2MotorGatewayError("SpeedPercent must be between -100 and 100.")
            return
        if max_speed is not None and isinstance(value, (int, float)) and abs(float(value)) > max_speed:
            raise Ev3Dev2MotorGatewayError("Speed exceeds the configured motor max_speed.")

    def _validate_property_value(self, obj, property_name, value):
        if property_name in ("ramp_up_sp", "ramp_down_sp") and (int(value) < 0 or int(value) > 10000):
            raise Ev3Dev2MotorGatewayError("Ramp value is outside the safe policy range.")
        if property_name == "stop_action" and value not in ("coast", "brake", "hold"):
            raise Ev3Dev2MotorGatewayError("Invalid stop_action.")

    def _validate_method(self, class_name, method_name):
        self._validate_public_name(method_name)
        if method_name not in self.ALLOWED_METHODS.get(class_name, ()):
            raise Ev3Dev2MotorGatewayError(
                "Method is not allowed for {}: {}".format(class_name, method_name)
            )

    def _supported_class(self, class_name):
        self._validate_public_name(class_name)
        if class_name not in self.SUPPORTED_CLASSES:
            raise Ev3Dev2MotorGatewayError("Unsupported class: {}".format(class_name))
        cls = getattr(self.module, class_name, None)
        if cls is None or not inspect.isclass(cls):
            raise Ev3Dev2MotorGatewayError("Supported class is unavailable: {}".format(class_name))
        return cls

    def _get(self, object_id):
        with self._lock:
            obj = self._objects.get(object_id)
        if obj is None:
            raise Ev3Dev2MotorGatewayError("Unknown object id: {}".format(object_id))
        return obj

    def _touch(self, object_id):
        with self._lock:
            if object_id in self._metadata:
                self._metadata[object_id]["last_used_at"] = time.time()

    def _object_operations(self, object_id):
        return [item for item in self._operations.values() if item["object_id"] == object_id]

    @staticmethod
    def _operation_view(operation):
        return dict((key, value) for key, value in operation.items() if key != "internal")

    @staticmethod
    def _invoke_result(object_id, method_name, kind, result, operation_id):
        return {
            "object_id": object_id,
            "method": method_name,
            "classification": kind,
            "operation_id": operation_id,
            "result": result if result is None or isinstance(result, (str, int, float, bool, list, dict)) else repr(result)
        }

    @staticmethod
    def _validate_public_name(name):
        if not isinstance(name, str) or not name or name.startswith("_"):
            raise Ev3Dev2MotorGatewayError("A public member name is required.")

    def _resolve(self, value):
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if isinstance(value, dict):
            if set(value.keys()) == set(["$ref"]):
                return self._get(value["$ref"])
            if "$speed" in value:
                speed_name = value["$speed"]
                if speed_name not in self.SPEED_CLASSES:
                    raise Ev3Dev2MotorGatewayError("Unsupported speed value class.")
                speed_class = getattr(self.module, speed_name, None)
                if speed_class is None or not inspect.isclass(speed_class):
                    raise Ev3Dev2MotorGatewayError("Official speed class is unavailable.")
                return speed_class(value.get("value"))
            if "$tuple" in value:
                return tuple(self._resolve(item) for item in value["$tuple"])
            return dict((key, self._resolve(item)) for key, item in value.items())
        return value

    def _serialize(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple, set)):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return dict((str(key), self._serialize(item)) for key, item in value.items())
        with self._lock:
            for object_id, obj in self._objects.items():
                if value is obj:
                    return {"$ref": object_id, "class": obj.__class__.__name__}
        if inspect.isclass(value):
            return {"class": value.__name__}
        if callable(value):
            return {"callable": getattr(value, "__name__", value.__class__.__name__)}
        return repr(value)
