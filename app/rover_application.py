#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application lifecycle orchestration through explicit output ports."""


class _NullLogger(object):
    @staticmethod
    def status(message):
        del message

    @staticmethod
    def error(message):
        del message


class ApplicationStartupError(RuntimeError):
    """Raised when a critical runtime dependency cannot initialize."""


class RoverApplication(object):
    """Coordinates already-assembled components without runtime primitives."""

    def __init__(self, rest_api_server, concurrency_port,
                 process_control_port,
                 monitor_registrations=None, managed_resources=None,
                 runtime_components=None, logger=None,
                 application_name="Rover DR", application_version="unknown"):
        if concurrency_port is None:
            raise ValueError("concurrency_port is required.")
        if process_control_port is None:
            raise ValueError("process_control_port is required.")
        self.rest_api_server = rest_api_server
        self.monitor_registrations = list(monitor_registrations or [])
        self.monitors = [item.component for item in self.monitor_registrations]
        self.managed_resources = list(managed_resources or [])
        self.runtime_components = list(runtime_components or [])
        self.logger = logger or _NullLogger
        self.application_name = application_name
        self.application_version = application_version
        self._concurrency = concurrency_port
        self._process_control = process_control_port
        self._configure_monitor_failure_policies()

    def start(self):
        if self._concurrency.is_stop_requested():
            return
        early_components = self._early_runtime_components()
        if early_components:
            self._start_runtime_components(early_components)
            self._prepare_runtime_components()
            if self._concurrency.is_stop_requested():
                return
            self._start_monitors()
            self._start_runtime_components(
                component for component in self.runtime_components
                if component not in early_components
            )
        else:
            self._start_monitors()
            self._prepare_runtime_components()
            self._start_runtime_components(self.runtime_components)
        self.rest_api_server.start()
        if self.is_restart_requested():
            if self._concurrency.wait_for_stop_completed(20.0):
                self._restart_current_process()
                return
            self.logger.error(
                "Restart aborted because application shutdown did not complete."
            )

    def stop(self):
        if not self._concurrency.claim_stop():
            self._concurrency.wait_for_stop_completed(20.0)
            return
        self.logger.status(
            "Stopping {} {}.".format(
                self.application_name, self.application_version
            )
        )
        try:
            self._prepare_monitors_for_shutdown()
            self.rest_api_server.stop()
            self._stop_runtime_components()
            self._stop_monitors()
            self._close_managed_resources()
            self._join_monitors()
            self.logger.status("Rover application stopped.")
        finally:
            self._concurrency.mark_stop_completed()

    def request_shutdown(self):
        """Schedules one asynchronous shutdown through the concurrency port."""
        if not self._concurrency.claim_shutdown_request():
            return False
        self.logger.status("Shutdown request received.")
        self._concurrency.run_async(
            self.stop,
            "ApplicationShutdownThread",
            False
        )
        return True

    def request_restart(self):
        """Schedules one asynchronous restart through the concurrency port."""
        if not self._concurrency.claim_restart_request():
            return False
        self.logger.status("Remote Rover application restart requested.")
        self._concurrency.run_async(
            self.stop,
            "ApplicationRestartThread",
            False
        )
        return True

    def is_restart_requested(self):
        return self._concurrency.is_restart_requested()

    def _prepare_runtime_components(self):
        """Runs optional synchronous preparation after early UI startup."""
        for component in self.runtime_components:
            prepare_start = getattr(component, "prepare_start", None)
            if callable(prepare_start):
                prepare_start()

    def _early_runtime_components(self):
        """Returns components that must be visible before startup checks."""
        return [
            component for component in self.runtime_components
            if bool(getattr(
                component, "start_before_startup_checks", False
            ))
        ]

    @staticmethod
    def _start_runtime_components(components):
        for component in components:
            component.start()

    def _restart_current_process(self):
        self._process_control.restart_current_process()

    def _prepare_monitors_for_shutdown(self):
        for monitor in self.monitors:
            try:
                monitor.prepare_for_shutdown()
            except Exception as error:
                self.logger.error(
                    "Failed to prepare {} Monitor for shutdown: {}".format(
                        monitor.get_monitor_name(), error
                    )
                )

    def _stop_runtime_components(self):
        for component in reversed(self.runtime_components):
            try:
                component.stop()
            except Exception as error:
                self.logger.error(
                    "Failed to stop runtime component {}: {}".format(
                        component.__class__.__name__, error
                    )
                )

    def _stop_monitors(self):
        for monitor in self.monitors:
            self.logger.status(
                "Stopping {} Monitor.".format(monitor.get_monitor_name())
            )
            monitor.stop()

    def _close_managed_resources(self):
        for resource in reversed(self.managed_resources):
            try:
                resource.close()
            except Exception as error:
                self.logger.error(
                    "Failed to close managed resource {}: {}".format(
                        resource.__class__.__name__, error
                    )
                )

    def _join_monitors(self):
        for monitor in self.monitors:
            if self._concurrency.is_current_component(monitor):
                continue
            monitor.join(timeout=5.0)
            if monitor.is_alive():
                self.logger.error(
                    "Failed to stop {} Monitor.".format(
                        monitor.get_monitor_name()
                    )
                )
            else:
                self.logger.status(
                    "{} Monitor stopped.".format(monitor.get_monitor_name())
                )

    def _configure_monitor_failure_policies(self):
        for registration in self.monitor_registrations:
            registration.component.set_failure_policy(
                critical=registration.critical,
                failure_handler=self._handle_monitor_failure
            )

    def _handle_monitor_failure(self, monitor, error):
        if not monitor.is_critical():
            return
        if not self._concurrency.claim_critical_shutdown():
            return
        self.logger.error(
            "Critical failure detected in {} Monitor. Stopping Rover "
            "application. Error: {}".format(
                monitor.get_monitor_name(), error
            )
        )
        self._concurrency.run_async(
            self.stop,
            "CriticalMonitorFailureShutdownThread",
            True
        )

    def _start_monitors(self):
        for registration in self.monitor_registrations:
            monitor = registration.component
            self.logger.status(
                "Starting {} Monitor.".format(registration.name)
            )
            monitor.start()

        for registration in self.monitor_registrations:
            monitor = registration.component
            if monitor.wait_until_initialized(timeout_seconds=5.0):
                self.logger.status(
                    "{} Monitor ready.".format(registration.name)
                )
                continue

            if monitor.has_failed():
                failure_state = self._get_monitor_failure_state(monitor)
                failure_message = failure_state.get(
                    "failure_message"
                ) or "unknown monitor initialization error"
                startup_error = ApplicationStartupError(
                    "{0} Monitor failed during initialization: {1}".format(
                        registration.name, failure_message
                    )
                )
                self.logger.error(str(startup_error))
                if monitor.is_critical():
                    self._handle_monitor_failure(monitor, startup_error)
                    raise startup_error
                continue

            startup_error = ApplicationStartupError(
                "{0} Monitor did not initialize within 5 seconds.".format(
                    registration.name
                )
            )
            self.logger.error(str(startup_error))
            if monitor.is_critical():
                self._handle_monitor_failure(monitor, startup_error)
                raise startup_error

    @staticmethod
    def _get_monitor_failure_state(monitor):
        get_failure_state = getattr(monitor, "get_failure_state", None)
        if callable(get_failure_state):
            return get_failure_state()
        return {
            "failed": monitor.has_failed(),
            "critical": monitor.is_critical(),
            "failure_type": None,
            "failure_message": None
        }
