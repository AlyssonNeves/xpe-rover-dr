#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Single composition root for startup and all Rover execution graphs."""

from adapters.in_evdev_joystick import EvdevJoystickAdapter
from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_ev3_command_control_selector import (
    Ev3CommandControlSelectorAdapter
)
from adapters.out_ev3_local_drive_setup_selector import (
    Ev3LocalDriveSetupSelectorAdapter
)
from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_ev3_operation_status import Ev3OperationStatusAdapter
from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from adapters.out_ev3_status_led import Ev3StatusLedAdapter
from adapters.out_local_manual_queries import (
    FieldManualSensorQueryAdapter,
    LocalManualControllerQueryAdapter,
    LocalManualMotorQueryAdapter,
    LocalManualSensorQueryAdapter
)
from adapters.out_heading_state import HeadingStateQueryAdapter
from adapters.out_ev3_gyro_sensor import Ev3GyroSensorAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_motor_state_publisher import MotorStateStorePublisherAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from app.command_service import CommandService
from app.operation_mode_service import (
    Centrics,
    Commands,
    Drives,
    OperationModeService,
    coerce_operation_mode
)
from app.monitor_registration import MonitorRegistration
from app import rover_application as rover_application_module
from app.rover_config import DEFAULT_CONFIGURATION
from app.services.drive_service import DriveService
from app.services.field_heading_reference_service import (
    FieldHeadingReferenceService
)
from app.services.joystick_control_service import JoystickControlService
from app.services.manual_drive_service import ManualDriveService
from app.services.rover_state_service import RoverStateService
from app.services.startup_error_notifier import StartupErrorNotifier
from infrastructure.configuration.rover_configuration_loader import (
    RoverConfigurationLoader
)
from infrastructure.ev3.ev3dev2_motor_gateway import (
    Ev3Dev2MotorGateway,
    Ev3Dev2MotorGatewayError
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
from ports.joystick_connection_status_port import (
    JoystickConnectionStatusPort
)
from ports.startup_progress_port import StartupProgressPort
from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.state.heading_state_store import HeadingStateStore
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.state.sensor_state_store import SensorStateStore

ApplicationStartupError = rover_application_module.ApplicationStartupError
RoverApplication = rover_application_module.RoverApplication


def prepare_rover_runtime(configuration_loader=None, logger=None):
    """Loads configuration, selects one cohesive operation mode and assembles it."""
    active_logger = logger or AppLogger
    loader = configuration_loader or RoverConfigurationLoader()
    active_logger.status("Starting Rover application.")
    _prepare_startup_alert_resources(loader)
    try:
        configuration = loader.load()
    except RuntimeError as error:
        _report_startup_error(loader, active_logger, error)
        return RoverRuntimeContext(logger=active_logger, exit_code=1)

    operation_mode_service = OperationModeService()
    operation_status_component = None
    if configuration.hardware_enabled:
        _prepare_ev3_screen_cache(active_logger)
        operation_mode_service = OperationModeService(
            command_control_selector_port=Ev3CommandControlSelectorAdapter(),
            local_drive_selector_port=Ev3LocalDriveSetupSelectorAdapter()
        )
        while True:
            active_logger.status(
                "Waiting for the operator to select Command and Control."
            )
            selected_mode = operation_mode_service.select_command_control()
            if selected_mode is None:
                active_logger.status("Rover startup cancelled by the operator.")
                return RoverRuntimeContext(logger=active_logger, exit_code=1)

            if selected_mode["command"] != Commands.LOCAL:
                break

            active_logger.status(
                "Waiting for the operator to select Front, Drive and Mode."
            )
            selected_mode = operation_mode_service.select_local_drive()
            if selected_mode is None:
                active_logger.status("Rover startup cancelled by the operator.")
                return RoverRuntimeContext(logger=active_logger, exit_code=1)
            if selected_mode.get("navigation") == "BACK":
                continue
            break

        startup_gated = operation_mode_service.get_mode().is_local_manual()
        operation_status_component = Ev3OperationStatusAdapter(
            operation_mode_service=operation_mode_service,
            joystick_device_name=configuration.joystick_device_name,
            startup_gated=startup_gated
        )
        if startup_gated:
            # Match Command/Control -> Front/Drive: paint the destination first,
            # emit its three-beep prompt, and only then assemble/check hardware.
            start_status = getattr(operation_status_component, "start", None)
            if callable(start_status):
                start_status()
    else:
        selected_mode = operation_mode_service.get_snapshot()

    active_logger.status(
        "Rover operation mode selected: command={0}, control={1}, front={2}, "
        "drive={3}, centric={4}, differential_mode={5}.".format(
            selected_mode["command"],
            selected_mode["control"],
            selected_mode["front"],
            selected_mode["drive"],
            selected_mode["centric"],
            selected_mode["differential_mode"]
        )
    )
    application = build_rover_application(
        configuration=configuration,
        operation_mode_service=operation_mode_service,
        operation_status_component=operation_status_component,
        logger=active_logger
    )
    return RoverRuntimeContext(
        application=application, logger=active_logger, exit_code=0
    )


def _prepare_startup_alert_resources(loader):
    """Warms only the fatal-screen render resources before validation."""
    try:
        if loader.hardware_requested() is True:
            Ev3OperatorAlertAdapter.prepare_render_resources()
    except (
            ImportError, IOError, OSError, RuntimeError, AttributeError,
            TypeError, ValueError):
        # Startup validation must remain authoritative.  If the warm-up cannot
        # run, the alert adapter will retry the same resources only if needed.
        return


def _prepare_ev3_screen_cache(logger):
    """Preloads ready-to-use PBM screens without converting source artwork."""
    result = warm_monochrome_screen_cache()
    logger.status(
        "EV3 PBM screens ready: {0} screen(s), {1} memory hit(s), "
        "{2} loaded from cache.".format(
            result["total"],
            result["memory_hits"],
            result["loaded"]
        )
    )
    if result["failed"]:
        logger.warning(
            "EV3 screen cache could not load {0} PBM screen(s); affected "
            "screens will retry during display.".format(
                len(result["failed"])
            )
        )


def _report_startup_error(loader, logger, error):
    logger.error("Configuration error: {0}".format(error))
    if loader.hardware_requested():
        notifier = StartupErrorNotifier(Ev3OperatorAlertAdapter(
            status_led_factory=Ev3StatusLedAdapter,
            fault_source="configuration"
        ))
        logger.status(
            "Waiting for the user to press any EV3 button to terminate the program."
        )
        if not notifier.show(str(error)):
            logger.status("EV3 startup alert could not be displayed.")
    else:
        logger.status(
            "EV3 startup alert skipped because motor hardware is disabled."
        )


def build_rover_application(configuration=None,
                            operation_status_component=None, logger=None,
                            operation_mode_service=None):
    """Builds the graph selected by the canonical operation-mode structure."""
    config = configuration or DEFAULT_CONFIGURATION
    mode_service = _resolve_operation_mode_service(operation_mode_service)
    if mode_service.get_mode().is_local_manual():
        return build_local_manual_application(
            configuration=config,
            operation_mode_service=mode_service,
            operation_status_component=operation_status_component,
            logger=logger
        )
    return build_standard_application(
        config,
        operation_mode_service=mode_service,
        operation_status_component=operation_status_component,
        logger=logger
    )


def _resolve_operation_mode_service(operation_mode_service=None):
    """Returns one canonical service for every application graph."""
    if isinstance(operation_mode_service, OperationModeService):
        return operation_mode_service
    return _operation_mode_service_from_value(operation_mode_service)


def _operation_mode_service_from_value(value):
    mode = coerce_operation_mode(value)
    if mode.command == Commands.REMOTE:
        return OperationModeService(command=Commands.REMOTE)
    return OperationModeService(
        command=mode.command,
        control=mode.control,
        front=mode.front,
        drive=mode.drive,
        centric=mode.centric,
        differential_mode=mode.differential_mode
    )


def build_local_manual_application(configuration,
                                   operation_status_component=None,
                                   logger=None,
                                   operation_mode_service=None):
    """Builds the minimal deterministic LOCAL + MANUAL joystick graph."""
    active_logger = logger or AppLogger
    mode_service = _resolve_operation_mode_service(operation_mode_service)
    operation_mode = mode_service.get_mode()
    motor_state_store = MotorStateStore()

    monitor_registrations = []
    canonical_heading_query_port = None
    heading_query_port = None
    field_heading_reference_port = None
    state_monitors = {}
    sensor_query_port = LocalManualSensorQueryAdapter(
        configuration.sensor_definitions
    )

    is_field_mode = (
        operation_mode.drive == Drives.MECANUM and
        operation_mode.centric == Centrics.FIELD
    )
    if is_field_mode:
        if not configuration.hardware_enabled:
            raise RuntimeError(
                "FIELD-centric Mecanum control requires EV3 hardware."
            )
        heading_config = configuration.field_heading
        gyro_sensor_code = heading_config["sensor_code"]
        gyro_definition = configuration.sensor_definitions.get(
            gyro_sensor_code
        )
        if gyro_definition is None:
            raise RuntimeError(
                "FIELD heading sensor definition not found: {0}.".format(
                    gyro_sensor_code
                )
            )

        heading_store = HeadingStateStore()
        canonical_heading_query_port = HeadingStateQueryAdapter(
            heading_store,
            max_age_seconds=float(
                heading_config["max_age_seconds"]
            )
        )
        field_heading_reference_port = FieldHeadingReferenceService(
            canonical_heading_query_port
        )
        heading_query_port = field_heading_reference_port
        gyro_hardware = Ev3GyroSensorAdapter(
            address=gyro_definition["address"],
            mode=gyro_definition["mode"],
            reset_on_start=bool(heading_config["reset_on_start"]),
            angle_sign=float(heading_config["angle_sign"]),
            angle_offset_deg=float(heading_config["angle_offset_deg"]),
            port_mode=gyro_definition.get("port_mode"),
            connection_timeout_seconds=float(
                heading_config["connection_timeout_seconds"]
            ),
            connection_retry_seconds=float(
                heading_config["connection_retry_seconds"]
            )
        )
        gyro_monitor = GyroHeadingMonitor(
            heading_sensor_port=gyro_hardware,
            state_store=heading_store,
            sensor_code=gyro_sensor_code,
            address=gyro_definition["address"],
            mode=gyro_definition["mode"],
            interval_seconds=float(
                heading_config["poll_seconds"]
            ),
            max_consecutive_failures=int(
                heading_config["max_consecutive_failures"]
            )
        )
        monitor_registrations.append(
            MonitorRegistration(gyro_monitor, "Gyro Heading", True)
        )
        state_monitors["gyro_heading"] = gyro_monitor
        sensor_query_port = FieldManualSensorQueryAdapter(
            configuration.sensor_definitions,
            gyro_sensor_code=gyro_sensor_code,
            heading_query_port=canonical_heading_query_port
        )

    hardware_adapter = Ev3MotorHardwareAdapter(
        motor_definitions=configuration.motor_definitions,
        default_stop_action=configuration.motor_default_stop_action
    )
    motor_query_port = LocalManualMotorQueryAdapter(
        motor_state_store,
        configuration.motor_definitions,
        motor_hardware_port=(
            hardware_adapter if configuration.hardware_enabled else None
        )
    )
    controller_port = LocalManualControllerQueryAdapter()

    state_service = RoverStateService(
        sensor_query_port=sensor_query_port,
        motor_query_port=motor_query_port,
        controller_port=controller_port,
        monitors=state_monitors,
        operation_mode_service=mode_service
    )
    command_service = CommandService(
        sensor_query_port=sensor_query_port,
        motor_query_port=motor_query_port,
        controller_port=controller_port,
        rover_state_query_port=state_service,
        operation_mode_service=mode_service
    )
    rest_server = _build_rest_server(
        command_service, configuration, motor_gateway_port=None
    )

    runtime_components = []
    active_status_component = operation_status_component
    status_led_component = None
    if configuration.hardware_enabled:
        status_led_component = Ev3StatusLedAdapter(
            operation_mode_service=mode_service,
            motor_query_port=None,
            logger=active_logger
        )
        runtime_components.append(status_led_component)
        active_status_component = (
            operation_status_component or Ev3OperationStatusAdapter(
                operation_mode_service=mode_service,
                joystick_device_name=configuration.joystick_device_name,
                startup_gated=True
            )
        )
        if hasattr(active_status_component, "set_motor_query_port"):
            active_status_component.set_motor_query_port(motor_query_port)
        runtime_components.append(active_status_component)

    state_publisher = MotorStateStorePublisherAdapter(motor_state_store)
    joystick_connection_status_port = None
    startup_progress_port = None
    if isinstance(
            active_status_component, JoystickConnectionStatusPort):
        joystick_connection_status_port = active_status_component
    if isinstance(active_status_component, StartupProgressPort):
        startup_progress_port = active_status_component

    manual_drive_service = ManualDriveService(
        motor_hardware_port=hardware_adapter,
        motor_state_publisher_port=state_publisher,
        drive_config=configuration.drive,
        mecanum_config=configuration.mecanum,
        joystick_config=configuration.joystick,
        default_stop_action=configuration.motor_default_stop_action,
        logger=active_logger,
        startup_progress_port=startup_progress_port,
        status_led_port=status_led_component
    )
    joystick_adapter = EvdevJoystickAdapter(
        device_name=configuration.joystick_device_name,
        device_address=configuration.joystick["device_address"],
        auto_connect=bool(configuration.joystick["auto_connect"]),
        connection_timeout_seconds=float(
            configuration.joystick["connection_timeout_seconds"]
        ),
        passive_reconnect_seconds=float(
            configuration.joystick["passive_reconnect_seconds"]
        ),
        discovery_poll_seconds=float(
            configuration.joystick["discovery_poll_seconds"]
        )
    )
    joystick_service = JoystickControlService(
        joystick_port=joystick_adapter,
        manual_drive_port=manual_drive_service,
        device_name=configuration.joystick_device_name,
        max_speed_sp=int(configuration.joystick["max_speed_sp"]),
        auxiliary_speed_sp=int(configuration.joystick["auxiliary_speed_sp"]),
        axis_center=int(configuration.joystick["axis_center"]),
        axis_deadzone=int(configuration.joystick["axis_deadzone"]),
        axis_max=int(configuration.joystick["axis_max"]),
        axis_response_intensity=float(
            configuration.joystick["axis_response_intensity"]
        ),
        neutral_stability_seconds=float(
            configuration.joystick["neutral_stability_seconds"]
        ),
        neutral_poll_seconds=float(
            configuration.joystick["neutral_poll_seconds"]
        ),
        left_auxiliary_motor_code=(
            configuration.joystick["left_auxiliary_motor_code"]
        ),
        right_auxiliary_motor_code=(
            configuration.joystick["right_auxiliary_motor_code"]
        ),
        poll_seconds=float(configuration.joystick["poll_seconds"]),
        connection_retry_seconds=float(
            configuration.joystick["connection_retry_seconds"]
        ),
        operation_mode=operation_mode,
        mecanum_strafe_compensation=float(
            configuration.mecanum["strafe_compensation"]
        ),
        heading_query_port=heading_query_port,
        field_heading_reference_port=field_heading_reference_port,
        stop_button_code=int(
            configuration.joystick["button_codes"]["emergency_stop"]
        ),
        field_recenter_button_code=int(
            configuration.joystick["button_codes"]["field_recenter"]
        ),
        field_recenter_enabled=bool(
            configuration.field_heading["runtime_recenter_enabled"]
        ),
        field_recenter_requires_neutral=bool(
            configuration.field_heading["recenter_requires_neutral"]
        ),
        logger=active_logger,
        connection_status_port=joystick_connection_status_port,
        startup_progress_port=startup_progress_port,
        status_led_port=status_led_component
    )
    runtime_components.extend([manual_drive_service, joystick_service])

    if is_field_mode:
        active_logger.status(
            "LOCAL + MANUAL FIELD mode: only the dedicated gyro heading "
            "monitor, joystick session, synchronous motor hardware adapter, "
            "status display and read-only REST queries are active."
        )
    else:
        active_logger.status(
            "LOCAL + MANUAL mode: front={0}, drive={1}, centric={2}, "
            "differential_mode={3}; only the joystick session, synchronous "
            "motor hardware adapter, status display and read-only REST "
            "queries are active.".format(
                operation_mode.front,
                operation_mode.drive,
                operation_mode.centric,
                operation_mode.differential_mode
            )
        )
    return _finalize_application(
        configuration, rest_server, monitor_registrations,
        runtime_components, [], active_logger
    )


def build_standard_application(configuration,
                               operation_status_component=None,
                               logger=None,
                               operation_mode_service=None):
    """Builds the monitored command, navigation and gateway graph."""
    active_logger = logger or AppLogger
    mode_service = _resolve_operation_mode_service(operation_mode_service)
    sensor_store = SensorStateStore()
    sensor_monitor = SensorMonitor(
        state_store=sensor_store,
        sensor_definitions=configuration.sensor_definitions
    )
    sensor_port = SensorMonitorAdapter(sensor_monitor, sensor_store)

    motor_store = MotorStateStore()
    motor_monitor = MotorMonitor(
        state_store=motor_store,
        motor_definitions=configuration.motor_definitions,
        hardware_enabled=configuration.hardware_enabled,
        configuration=configuration
    )
    motor_adapter = MotorMonitorAdapter(motor_monitor, motor_store)

    controller_store = ControllerStateStore()
    controller_monitor = ControllerMonitor(state_store=controller_store)
    controller_port = ControllerMonitorAdapter(
        controller_monitor, controller_store
    )

    registrations = [
        MonitorRegistration(controller_monitor, "Controller", False),
        MonitorRegistration(sensor_monitor, "Sensor", True),
        MonitorRegistration(motor_monitor, "Motor", True)
    ]
    state_service = RoverStateService(
        sensor_query_port=sensor_port,
        motor_query_port=motor_adapter,
        controller_port=controller_port,
        monitors={
            "controller": controller_monitor,
            "sensor": sensor_monitor,
            "motor": motor_monitor
        },
        operation_mode_service=mode_service
    )
    drive_service = DriveService(
        motor_query_port=motor_adapter,
        drive_motor_port=motor_adapter,
        motor_command_port=motor_adapter,
        motor_command_query_port=motor_adapter,
        sensor_port=sensor_port,
        config=configuration.drive
    )
    command_service = CommandService(
        sensor_query_port=sensor_port,
        sensor_command_port=sensor_port,
        motor_query_port=motor_adapter,
        controller_port=controller_port,
        rover_state_query_port=state_service,
        motor_command_port=motor_adapter,
        motor_command_query_port=motor_adapter,
        drive_motor_port=motor_adapter,
        drive_port=drive_service,
        operation_mode_service=mode_service
    )

    gateway = _build_gateway(configuration, motor_adapter, active_logger)
    rest_server = _build_rest_server(
        command_service, configuration, motor_gateway_port=gateway
    )
    runtime_components = []
    if configuration.hardware_enabled:
        status_led_component = Ev3StatusLedAdapter(
            operation_mode_service=mode_service,
            motor_query_port=motor_adapter,
            logger=active_logger
        )
        runtime_components.append(status_led_component)
        active_status_component = (
            operation_status_component or Ev3OperationStatusAdapter(
                operation_mode_service=mode_service,
                joystick_device_name=configuration.joystick_device_name
            )
        )
        if hasattr(active_status_component, "set_motor_query_port"):
            active_status_component.set_motor_query_port(motor_adapter)
        runtime_components.append(active_status_component)

    return _finalize_application(
        configuration,
        rest_server,
        registrations,
        runtime_components,
        [gateway] if gateway is not None else [],
        active_logger
    )


def _build_gateway(configuration, motor_adapter, logger):
    try:
        return Ev3Dev2MotorGateway(
            motor_query_port=motor_adapter,
            guarded_operation_port=motor_adapter,
            max_objects=configuration.motor_gateway_max_objects,
            object_ttl_seconds=(
                configuration.motor_gateway_object_ttl_seconds
            ),
            max_watchdog_ms=configuration.motor_gateway_max_watchdog_ms,
            wait_max_timeout_ms=(
                configuration.motor_gateway_wait_max_timeout_ms
            )
        )
    except Ev3Dev2MotorGatewayError as error:
        logger.error(
            "Safe EV3Dev2 motor-domain gateway unavailable: {}".format(error)
        )
        return None


def _build_rest_server(command_service, configuration, motor_gateway_port):
    return RestApiServer(
        command_service=command_service,
        host=configuration.rest_host,
        port=configuration.rest_port,
        motor_gateway_port=motor_gateway_port,
        shutdown_token=configuration.shutdown_token,
        hardware_api_token=configuration.hardware_api_token,
        shutdown_confirmation_required=(
            configuration.shutdown_confirmation_required
        )
    )


def _finalize_application(configuration, rest_server, monitor_registrations,
                          runtime_components, managed_resources, logger):
    application = RoverApplication(
        rest_api_server=rest_server,
        monitor_registrations=monitor_registrations,
        managed_resources=managed_resources,
        runtime_components=runtime_components,
        logger=logger,
        concurrency_port=ThreadingApplicationConcurrency(),
        process_control_port=OsProcessController(),
        application_name=configuration.application_name,
        application_version=configuration.application_version
    )
    rest_server.set_shutdown_callback(application.request_shutdown)
    rest_server.set_restart_callback(application.request_restart)
    return application
