#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Single composition root for Rover-DR execution graphs."""

from adapters.in_evdev_joystick import EvdevJoystickAdapter
from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_drive_service import DriveServiceAdapter
from adapters.out_ev3_command_control_selector import Ev3CommandControlSelectorAdapter
from adapters.out_ev3_local_drive_setup_selector import Ev3LocalDriveSetupSelectorAdapter
from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_ev3_gyro_sensor import Ev3GyroSensorAdapter
from adapters.out_heading_state import HeadingStateQueryAdapter
from adapters.out_ev3_operation_status import Ev3OperationStatusAdapter
from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from adapters.out_local_manual_queries import (
    FieldManualSensorQueryAdapter,
    LocalManualControllerQueryAdapter,
    LocalManualMotorQueryAdapter,
    LocalManualSensorQueryAdapter
)
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_motor_state_publisher import MotorStateStorePublisherAdapter
from adapters.out_rover_state_query import RoverStateQueryAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from app import rover_config
from app.command_service import CommandService
from app.operation_mode_service import (
    Centrics, Commands, Controls, Drives, OperationModeService
)
from app.monitor_registration import MonitorRegistration
from app.rover_application import ApplicationStartupError, RoverApplication
from app.services.drive_service import DriveService
from app.services.field_heading_reference_service import FieldHeadingReferenceService
from app.services.joystick_control_service import JoystickControlService
from app.services.manual_drive_service import ManualDriveService
from app.services.rover_state_service import RoverStateService
from app.services.startup_error_notifier import StartupErrorNotifier
from infrastructure.ev3.ev3dev2_motor_gateway import (
    Ev3Dev2MotorGateway, Ev3Dev2MotorGatewayError
)
from infrastructure.ev3.screen_image import warm_monochrome_screen_cache
from infrastructure.logging.app_logger import AppLogger
from infrastructure.monitoring.controller_monitor import ControllerMonitor
from infrastructure.monitoring.gyro_heading_monitor import GyroHeadingMonitor
from infrastructure.monitoring.motor_monitor import MotorMonitor
from infrastructure.monitoring.sensor_monitor import SensorMonitor
from infrastructure.runtime.os_process_controller import OsProcessController
from infrastructure.runtime.rover_runtime_context import RoverRuntimeContext
from infrastructure.runtime.threading_application_concurrency import (
    ThreadingApplicationConcurrency
)
from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.state.heading_state_store import HeadingStateStore
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.state.sensor_state_store import SensorStateStore


def _is_local_manual(operation_mode_service):
    if operation_mode_service is None:
        return True
    return operation_mode_service.get_mode().is_local_manual()


def build_rover_application(operation_mode_service=None, joystick_port=None,
                            heading_query_port=None):
    """Builds the execution graph selected by Command & Control."""
    if _is_local_manual(operation_mode_service):
        return build_local_manual_application(
            operation_mode_service=operation_mode_service,
            joystick_port=joystick_port,
            heading_query_port=heading_query_port
        )
    return build_standard_application(
        operation_mode_service=operation_mode_service
    )


def build_local_manual_application(operation_mode_service=None,
                                   joystick_port=None,
                                   heading_query_port=None):
    """Builds the minimal deterministic LOCAL + MANUAL runtime graph."""
    mode_service = operation_mode_service or OperationModeService()
    operation_mode = mode_service.get_mode()
    if not operation_mode.is_local_manual():
        raise RuntimeError(
            "LOCAL + MANUAL runtime requires a LOCAL/MANUAL operation mode."
        )

    is_field_mode = (
        operation_mode.drive == Drives.MECANUM and
        operation_mode.centric == Centrics.FIELD
    )
    if is_field_mode and heading_query_port is None and not rover_config.HARDWARE_ENABLED:
        raise RuntimeError(
            "FIELD-centric Mecanum control requires EV3 hardware or an "
            "injected cached heading source."
        )

    motor_state_store = MotorStateStore()
    sensor_definitions = rover_config.get_sensor_definitions()
    monitor_registrations = []
    canonical_heading_query_port = heading_query_port

    if is_field_mode and heading_query_port is None:
        heading_config = rover_config.get_field_heading_config()
        gyro_sensor_code = heading_config.get("sensor_code", "GYR")
        gyro_definition = sensor_definitions.get(gyro_sensor_code)
        if gyro_definition is None:
            raise RuntimeError(
                "FIELD heading sensor definition not found: {0}.".format(
                    gyro_sensor_code
                )
            )

        heading_store = HeadingStateStore()
        heading_query_port = HeadingStateQueryAdapter(
            heading_store,
            max_age_seconds=heading_config.get("max_age_seconds", 0.1)
        )
        canonical_heading_query_port = heading_query_port
        gyro_hardware = Ev3GyroSensorAdapter(
            address=gyro_definition.get("address", "in3"),
            mode=gyro_definition.get("mode", "GYRO-ANG"),
            reset_on_start=heading_config.get("reset_on_start", True),
            angle_sign=heading_config.get("angle_sign", -1.0),
            angle_offset_deg=heading_config.get("angle_offset_deg", 0.0),
            port_mode=gyro_definition.get("port_mode", "ev3-uart"),
            connection_timeout_seconds=heading_config.get(
                "connection_timeout_seconds", 10.0
            ),
            connection_retry_seconds=heading_config.get(
                "connection_retry_seconds", 0.1
            )
        )
        gyro_monitor = GyroHeadingMonitor(
            heading_sensor_port=gyro_hardware,
            state_store=heading_store,
            sensor_code=gyro_sensor_code,
            address=gyro_definition.get("address", "in3"),
            mode=gyro_definition.get("mode", "GYRO-ANG"),
            interval_seconds=heading_config.get("poll_seconds", 0.02),
            max_consecutive_failures=heading_config.get(
                "max_consecutive_failures", 3
            )
        )
        monitor_registrations.append(
            MonitorRegistration(gyro_monitor, "Gyro Heading", True)
        )
        sensor_port = FieldManualSensorQueryAdapter(
            sensor_definitions,
            gyro_sensor_code=gyro_sensor_code,
            heading_query_port=heading_query_port
        )
    elif is_field_mode and heading_query_port is not None:
        canonical_heading_query_port = heading_query_port
        gyro_sensor_code = rover_config.get_field_heading_config().get(
            "sensor_code", "GYR"
        )
        sensor_port = FieldManualSensorQueryAdapter(
            sensor_definitions,
            gyro_sensor_code=gyro_sensor_code,
            heading_query_port=heading_query_port
        )
    else:
        sensor_port = LocalManualSensorQueryAdapter(sensor_definitions)

    field_heading_reference_port = None
    if is_field_mode:
        field_heading_reference_port = FieldHeadingReferenceService(
            canonical_heading_query_port
        )
        heading_query_port = field_heading_reference_port

    motor_port = LocalManualMotorQueryAdapter(
        motor_state_store,
        rover_config.get_motor_definitions()
    )
    controller_port = LocalManualControllerQueryAdapter()

    rover_state_service = RoverStateService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        operation_mode_service=mode_service
    )
    rover_state_port = RoverStateQueryAdapter(rover_state_service)
    command_service = CommandService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        rover_state_port=rover_state_port,
        drive_port=None,
        operation_mode_service=mode_service
    )

    rest_api = RestApiServer(
        command_service,
        rover_config.REST_HOST,
        rover_config.REST_PORT,
        ev3dev2_motor_gateway=None
    )

    joystick_config = rover_config.get_joystick_config()
    motor_hardware_port = Ev3MotorHardwareAdapter(
        motor_definitions=rover_config.get_motor_definitions(),
        default_stop_action=rover_config.MOTOR_DEFAULT_STOP_ACTION
    )
    motor_state_publisher_port = MotorStateStorePublisherAdapter(
        motor_state_store
    )
    manual_drive_port = ManualDriveService(
        motor_hardware_port=motor_hardware_port,
        drive_config=rover_config.get_drive_config(),
        mecanum_config=rover_config.get_mecanum_config(),
        joystick_config=joystick_config,
        default_stop_action=rover_config.MOTOR_DEFAULT_STOP_ACTION,
        motor_state_publisher_port=motor_state_publisher_port
    )

    if joystick_port is None and rover_config.HARDWARE_ENABLED:
        joystick_port = EvdevJoystickAdapter(
            device_name=joystick_config.get(
                "device_name", "Wireless Controller"
            ),
            device_address=joystick_config.get("device_address", ""),
            auto_connect=joystick_config.get("auto_connect", True),
            connection_timeout_seconds=joystick_config.get(
                "connection_timeout_seconds", 10.0
            ),
            passive_reconnect_seconds=joystick_config.get(
                "passive_reconnect_seconds", 4.0
            ),
            discovery_poll_seconds=joystick_config.get(
                "discovery_poll_seconds", 0.25
            )
        )

    runtime_components = []
    managed_resources = [manual_drive_port]
    joystick_connection_status_port = None
    if rover_config.HARDWARE_ENABLED:
        joystick_connection_status_port = Ev3OperationStatusAdapter(
            operation_mode_service=mode_service,
            joystick_device_name=joystick_config.get(
                "device_name", "Wireless Controller"
            )
        )
        runtime_components.append(joystick_connection_status_port)

    if joystick_port is not None:
        joystick_control_service = JoystickControlService(
            joystick_port=joystick_port,
            manual_drive_port=manual_drive_port,
            max_speed_sp=joystick_config.get("max_speed_sp", 600),
            auxiliary_speed_sp=joystick_config.get(
                "auxiliary_speed_sp", 400
            ),
            axis_center=joystick_config.get("axis_center", 127),
            axis_deadzone=joystick_config.get("axis_deadzone", 7),
            axis_max=joystick_config.get("axis_max", 255),
            axis_response_intensity=joystick_config.get(
                "axis_response_intensity", 1.0
            ),
            left_auxiliary_motor_code=joystick_config.get(
                "left_auxiliary_motor_code", "LMM"
            ),
            right_auxiliary_motor_code=joystick_config.get(
                "right_auxiliary_motor_code", "RMM"
            ),
            drive_mode=operation_mode.drive,
            front=operation_mode.front,
            centric=operation_mode.centric or Centrics.CHASSIS,
            mecanum_strafe_compensation=rover_config.get_mecanum_config().get(
                "strafe_compensation", 1.0
            ),
            poll_seconds=joystick_config.get("poll_seconds", 0.02),
            logger=AppLogger,
            device_name=joystick_config.get(
                "device_name", "Wireless Controller"
            ),
            connection_retry_seconds=joystick_config.get(
                "connection_retry_seconds", 3.0
            ),
            connection_status_port=joystick_connection_status_port,
            heading_query_port=heading_query_port,
            field_heading_reference_port=field_heading_reference_port,
            emergency_stop_button_code=joystick_config.get(
                "button_codes", {}
            ).get("emergency_stop", 304),
            field_recenter_button_code=joystick_config.get(
                "button_codes", {}
            ).get("field_recenter", 307),
            field_recenter_enabled=rover_config.get_field_heading_config().get(
                "runtime_recenter_enabled", True
            ),
            field_recenter_requires_neutral=(
                rover_config.get_field_heading_config().get(
                    "recenter_requires_neutral", True
                )
            )
        )
        runtime_components.append(joystick_control_service)

    if is_field_mode:
        AppLogger.status(
            "LOCAL + MANUAL FIELD runtime: dedicated cached gyro heading, "
            "joystick and synchronous motor hardware are active; general "
            "sensor monitor queues remain disabled."
        )
    else:
        AppLogger.status(
            "LOCAL + MANUAL runtime: joystick, synchronous motor hardware, "
            "operation status and read-only REST queries are active; monitor "
            "queues and the EV3Dev2 motor gateway are disabled."
        )
    return _finalize_application(
        rest_api=rest_api,
        monitor_registrations=monitor_registrations,
        runtime_components=runtime_components,
        managed_resources=managed_resources
    )


def build_standard_application(operation_mode_service=None):
    """Builds the monitored runtime used outside LOCAL + MANUAL."""
    sensor_state_store = SensorStateStore()
    motor_state_store = MotorStateStore()
    controller_state_store = ControllerStateStore()

    sensor_monitor = SensorMonitor(state_store=sensor_state_store)
    motor_monitor = MotorMonitor(state_store=motor_state_store)
    controller_monitor = ControllerMonitor(state_store=controller_state_store)
    monitor_registrations = [
        MonitorRegistration(controller_monitor, "Controller", False),
        MonitorRegistration(sensor_monitor, "Sensor", True),
        MonitorRegistration(motor_monitor, "Motor", True)
    ]

    sensor_port = SensorMonitorAdapter(
        sensor_monitor=sensor_monitor, state_store=sensor_state_store
    )
    motor_port = MotorMonitorAdapter(
        motor_monitor=motor_monitor, state_store=motor_state_store
    )
    controller_port = ControllerMonitorAdapter(
        controller_monitor=controller_monitor,
        state_store=controller_state_store
    )

    rover_state_service = RoverStateService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        operation_mode_service=operation_mode_service
    )
    rover_state_port = RoverStateQueryAdapter(rover_state_service)

    drive_service = DriveService(motor_port=motor_port, sensor_port=sensor_port)
    drive_port = DriveServiceAdapter(drive_service)
    command_service = CommandService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        rover_state_port=rover_state_port,
        drive_port=drive_port,
        operation_mode_service=operation_mode_service
    )

    ev3dev2_motor_gateway = None
    if rover_config.HARDWARE_ENABLED:
        try:
            ev3dev2_motor_gateway = Ev3Dev2MotorGateway(
                motor_port=motor_port, drive_port=drive_port
            )
        except Ev3Dev2MotorGatewayError as error:
            AppLogger.warning(
                "EV3Dev2 motor gateway unavailable: {0}".format(error)
            )
    else:
        AppLogger.status(
            "Physical EV3 hardware is disabled; motor gateway was not started."
        )

    rest_api = RestApiServer(
        command_service,
        rover_config.REST_HOST,
        rover_config.REST_PORT,
        ev3dev2_motor_gateway=ev3dev2_motor_gateway
    )
    runtime_components = []
    managed_resources = []
    if ev3dev2_motor_gateway is not None:
        managed_resources.append(ev3dev2_motor_gateway)
    if rover_config.HARDWARE_ENABLED:
        joystick_config = rover_config.get_joystick_config()
        runtime_components.append(
            Ev3OperationStatusAdapter(
                operation_mode_service=operation_mode_service,
                joystick_device_name=joystick_config.get(
                    "device_name", "Wireless Controller"
                )
            )
        )
    return _finalize_application(
        rest_api=rest_api,
        monitor_registrations=monitor_registrations,
        runtime_components=runtime_components,
        managed_resources=managed_resources
    )



def _finalize_application(rest_api, monitor_registrations=None,
                          runtime_components=None, managed_resources=None):
    """Centralizes lifecycle ports and REST callbacks for every graph."""
    application = RoverApplication(
        rest_api_server=rest_api,
        monitor_registrations=monitor_registrations or [],
        runtime_components=runtime_components or [],
        managed_resources=managed_resources or [],
        logger=AppLogger,
        concurrency_port=ThreadingApplicationConcurrency(),
        process_control_port=OsProcessController(),
        application_name=rover_config.APPLICATION_NAME,
        application_version=rover_config.APPLICATION_VERSION
    )
    rest_api.set_shutdown_callback(application.request_shutdown)
    rest_api.set_restart_callback(application.request_restart)
    return application



def _prepare_ev3_screen_cache():
    """Preloads ready-to-use PBM screens without runtime conversion."""
    result = warm_monochrome_screen_cache()
    AppLogger.status(
        "EV3 PBM screens ready: {0} screen(s), {1} memory hit(s), "
        "{2} loaded from cache.".format(
            result["total"],
            result["memory_hits"],
            result["loaded"]
        )
    )
    if result["failed"]:
        AppLogger.warning(
            "EV3 screen cache could not load {0} PBM screen(s); affected "
            "screens will retry during display.".format(
                len(result["failed"])
            )
        )
    return result


def validate_startup_configuration():
    """Validates startup security and reports errors to the EV3 when possible."""
    try:
        rover_config.validate_security_configuration()
        return True
    except RuntimeError as error:
        AppLogger.error("Security configuration error: {0}".format(error))
        if rover_config.HARDWARE_ENABLED:
            startup_error_notifier = StartupErrorNotifier(
                Ev3OperatorAlertAdapter()
            )
            AppLogger.status(
                "Attempting to present the startup error on the EV3 brick."
            )
            if startup_error_notifier.show(str(error)):
                AppLogger.status(
                    "EV3 startup alert acknowledged by the operator."
                )
            else:
                AppLogger.status(
                    "EV3 startup alert unavailable; terminating startup."
                )
        else:
            AppLogger.status(
                "EV3 startup alert skipped because physical hardware is disabled."
            )
        return False


def select_operation_mode():
    """Selects the canonical Command/Control/Front/Drive/Centric mode."""
    if not rover_config.HARDWARE_ENABLED:
        service = OperationModeService()
        selected = service.get_snapshot()
        AppLogger.status(
            "Physical hardware disabled; using default "
            "LOCAL/MANUAL/NOSE/DIFFERENTIAL mode."
        )
        return service

    service = OperationModeService(
        command_control_selector_port=Ev3CommandControlSelectorAdapter(),
        local_drive_selector_port=Ev3LocalDriveSetupSelectorAdapter()
    )
    AppLogger.status(
        "Waiting for the operator to select Command and Control."
    )
    selected = service.select_command_control()
    if selected is None:
        AppLogger.status("Rover startup cancelled by the operator.")
        return None

    if selected["command"] == Commands.LOCAL:
        AppLogger.status(
            "Waiting for the operator to select Front, Drive and Centric."
        )
        selected = service.select_local_drive()
        if selected is None:
            AppLogger.status("Rover startup cancelled by the operator.")
            return None

    AppLogger.status(
        "Selected mode: command={0}, control={1}, front={2}, drive={3}, "
        "centric={4}.".format(
            selected["command"],
            selected["control"] or "N/A",
            selected["front"] or "N/A",
            selected["drive"] or "N/A",
            selected["centric"] or "N/A"
        )
    )
    return service


def prepare_rover_runtime():
    """Validates startup and returns one lifecycle-aware runtime context."""
    AppLogger.status("Starting Rover application.")
    if not validate_startup_configuration():
        return RoverRuntimeContext(logger=AppLogger, exit_code=1)
    if rover_config.HARDWARE_ENABLED:
        _prepare_ev3_screen_cache()
    operation_mode_service = select_operation_mode()
    if operation_mode_service is None:
        return RoverRuntimeContext(logger=AppLogger, exit_code=1)
    application = build_rover_application(
        operation_mode_service=operation_mode_service
    )
    return RoverRuntimeContext(
        application=application, logger=AppLogger, exit_code=0
    )


def prepare_rover_application():
    """Compatibility helper returning the assembled application, if ready."""
    runtime = prepare_rover_runtime()
    return runtime.application if runtime.ready else None


# Transitional aliases kept only for callers from the previous increment.
build_application = build_rover_application
_build_local_manual_application = build_local_manual_application
_build_standard_application = build_standard_application
