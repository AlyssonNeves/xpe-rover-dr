#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Single composition root for Rover-DR execution graphs."""

from adapters.in_evdev_joystick import EvdevJoystickAdapter
from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_drive_service import DriveServiceAdapter
from adapters.out_ev3_command_control_selector import Ev3CommandControlSelectorAdapter
from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_ev3_operation_status import Ev3OperationStatusAdapter
from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from adapters.out_local_manual_queries import (
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
from app.operation_mode_service import Commands, Controls, OperationModeService
from app.rover_application import RoverApplication
from app.services.drive_service import DriveService
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
from infrastructure.monitoring.motor_monitor import MotorMonitor
from infrastructure.monitoring.sensor_monitor import SensorMonitor
from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.state.sensor_state_store import SensorStateStore


def _is_local_manual(operation_mode_service):
    selected = (
        operation_mode_service.get_mode()
        if operation_mode_service is not None
        else {"command": Commands.LOCAL, "control": Controls.MANUAL}
    )
    return (
        selected.get("command") == Commands.LOCAL and
        selected.get("control") == Controls.MANUAL
    )


def build_rover_application(operation_mode_service=None, joystick_port=None):
    """Builds the execution graph selected by Command & Control."""
    if _is_local_manual(operation_mode_service):
        return build_local_manual_application(
            operation_mode_service=operation_mode_service,
            joystick_port=joystick_port
        )
    return build_standard_application(
        operation_mode_service=operation_mode_service
    )


def build_local_manual_application(operation_mode_service=None,
                                   joystick_port=None):
    """Builds the minimal deterministic LOCAL + MANUAL runtime graph."""
    mode_service = operation_mode_service or OperationModeService()
    motor_state_store = MotorStateStore()

    sensor_port = LocalManualSensorQueryAdapter(
        rover_config.get_sensor_definitions()
    )
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
            )
        )

    managed_services = []
    if rover_config.HARDWARE_ENABLED:
        managed_services.append(
            Ev3OperationStatusAdapter(
                operation_mode_service=mode_service,
                joystick_device_name=joystick_config.get(
                    "device_name", "Wireless Controller"
                )
            )
        )

    if joystick_port is not None:
        joystick_control_service = JoystickControlService(
            joystick_port=joystick_port,
            manual_drive_port=manual_drive_port,
            max_speed_sp=joystick_config.get("max_speed_sp", 600),
            auxiliary_speed_sp=joystick_config.get(
                "auxiliary_speed_sp", 400
            ),
            axis_center=joystick_config.get("axis_center", 127),
            axis_max=joystick_config.get("axis_max", 255),
            left_auxiliary_motor_code=joystick_config.get(
                "left_auxiliary_motor_code", "LMM"
            ),
            right_auxiliary_motor_code=joystick_config.get(
                "right_auxiliary_motor_code", "RMM"
            ),
            drive_mode="MECANUM",
            centric="CHASSIS",
            mecanum_strafe_compensation=rover_config.get_mecanum_config().get(
                "strafe_compensation", 1.0
            ),
            poll_seconds=joystick_config.get("poll_seconds", 0.02),
            logger=AppLogger
        )
        managed_services.extend([joystick_control_service, manual_drive_port])
    else:
        managed_services.append(manual_drive_port)

    AppLogger.status(
        "LOCAL + MANUAL runtime: joystick, synchronous motor hardware, "
        "operation status and read-only REST queries are active; monitor "
        "queues and the EV3Dev2 motor gateway are disabled."
    )
    application = RoverApplication(
        monitors=[], rest_api=rest_api, managed_services=managed_services,
        logger=AppLogger
    )
    rest_api.set_shutdown_callback(application.stop)
    rest_api.set_restart_callback(application.restart)
    return application


def build_standard_application(operation_mode_service=None):
    """Builds the monitored runtime used outside LOCAL + MANUAL."""
    sensor_state_store = SensorStateStore()
    motor_state_store = MotorStateStore()
    controller_state_store = ControllerStateStore()

    sensor_monitor = SensorMonitor(state_store=sensor_state_store)
    motor_monitor = MotorMonitor(state_store=motor_state_store)
    controller_monitor = ControllerMonitor(state_store=controller_state_store)
    monitors = [sensor_monitor, motor_monitor, controller_monitor]

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
    managed_services = []
    if ev3dev2_motor_gateway is not None:
        managed_services.append(ev3dev2_motor_gateway)
    if rover_config.HARDWARE_ENABLED:
        joystick_config = rover_config.get_joystick_config()
        managed_services.append(
            Ev3OperationStatusAdapter(
                operation_mode_service=operation_mode_service,
                joystick_device_name=joystick_config.get(
                    "device_name", "Wireless Controller"
                )
            )
        )
    application = RoverApplication(
        monitors=monitors,
        rest_api=rest_api,
        managed_services=managed_services,
        logger=AppLogger
    )
    rest_api.set_shutdown_callback(application.stop)
    rest_api.set_restart_callback(application.restart)
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
    """Selects Command & Control and returns its application service."""
    if not rover_config.HARDWARE_ENABLED:
        service = OperationModeService()
        AppLogger.status(
            "Physical hardware disabled; using default LOCAL/MANUAL mode."
        )
        return service

    service = OperationModeService(
        command_control_selector_port=Ev3CommandControlSelectorAdapter()
    )
    AppLogger.status("Waiting for the operator to select the Rover mode.")
    selected = service.select_command_control()
    if selected is None:
        AppLogger.status("Rover startup cancelled by the operator.")
        return None
    AppLogger.status(
        "Selected mode: {0}/{1}.".format(
            selected["command"], selected["control"] or "N/A"
        )
    )
    return service


def prepare_rover_application():
    """Validates startup, preloads EV3 screens and assembles one graph."""
    if not validate_startup_configuration():
        return None
    if rover_config.HARDWARE_ENABLED:
        _prepare_ev3_screen_cache()
    operation_mode_service = select_operation_mode()
    if operation_mode_service is None:
        return None
    return build_rover_application(
        operation_mode_service=operation_mode_service
    )


# Transitional aliases kept only for callers from the previous increment.
build_application = build_rover_application
_build_local_manual_application = build_local_manual_application
_build_standard_application = build_standard_application
