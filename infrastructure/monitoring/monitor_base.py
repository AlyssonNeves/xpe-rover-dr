#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base class for thread-based monitors in Rover.

This module is responsible for providing the shared lifecycle,
failure handling, and shutdown infrastructure for periodic monitors.
"""

import threading
import time

from infrastructure.logging.app_logger import AppLogger
from ports.monitor_diagnostics_port import MonitorDiagnosticsPort
from ports.monitor_lifecycle_port import MonitorLifecyclePort


class MonitorBase(
        threading.Thread, MonitorDiagnosticsPort, MonitorLifecyclePort):
    """Represents the base implementation for periodic Rover monitors."""

    def __init__(self, name, interval_seconds=1.0):
        """
        Initializes the monitor execution infrastructure.

        Args:
            name (str): Logical monitor name used to identify the thread.
            interval_seconds (float): Delay between monitor cycles.
        """
        threading.Thread.__init__(
            self,
            name="{0}Thread".format(name)
        )

        self.interval_seconds = interval_seconds

        # Events coordinate lifecycle state across the monitor thread and
        # the application orchestration code.
        self._stop_event = threading.Event()
        self._initialized_event = threading.Event()
        self._initialization_completed_event = threading.Event()
        self._failed_event = threading.Event()

        self._failure_type = None
        self._failure_message = None

        # Failure policy allows the application to distinguish diagnostic
        # monitor failures from failures that require application shutdown.
        self._critical_failure = False
        self._failure_handler = None

        self.daemon = True

    def run(self):
        """
        Executes the main monitor lifecycle.
        """
        AppLogger.status(
            "{} Monitor initializing.".format(
                self.get_monitor_name()
            )
        )

        try:
            self.on_initialize()

            self._initialized_event.set()
            self._initialization_completed_event.set()

            AppLogger.status(
                "{} Monitor initialized.".format(
                    self.get_monitor_name()
                )
            )

            while not self._stop_event.is_set():
                self.on_cycle()
                time.sleep(self.interval_seconds)

        except Exception as error:
            # Publish the complete failure state before releasing startup
            # waiters. This prevents a race where orchestration observes a
            # completed initialization without the registered exception.
            self._register_failure(error)
            self._initialization_completed_event.set()

            AppLogger.error(
                "Error in {} Monitor: {}".format(
                    self.get_monitor_name(),
                    error
                )
            )

            self._notify_failure_handler(error)

        finally:
            try:
                self.on_finalize()

            except Exception as error:
                AppLogger.error(
                    "Unexpected error finalizing {} Monitor: {}".format(
                        self.get_monitor_name(),
                        error
                    )
                )

            AppLogger.status(
                "{} Monitor finalized.".format(
                    self.get_monitor_name()
                )
            )

    def stop(self):
        """
        Requests the monitor shutdown.
        """
        self._stop_event.set()

    def prepare_for_shutdown(self):
        """Performs monitor-specific safety actions before shutdown."""
        return None

    def set_failure_policy(self, critical=False, failure_handler=None):
        """
        Defines how the application should react to monitor failures.

        Args:
            critical (bool):
                Indicates whether a monitor failure should be treated
                as critical to the application.
            failure_handler (callable, optional):
                Callback called when the monitor fails. It receives the
                monitor instance and the exception as arguments.
        """
        self._critical_failure = critical
        self._failure_handler = failure_handler

    def is_critical(self):
        """
        Checks whether this monitor is configured as critical.

        Returns:
            bool: True when the monitor failure is critical.
        """
        return self._critical_failure

    def wait_until_initialized(self, timeout_seconds=None):
        """
        Waits until the monitor initialization completes.

        Args:
            timeout_seconds (float, optional):
                Maximum time to wait for initialization completion.

        Returns:
            bool: True if initialization completed successfully.
        """
        self._initialization_completed_event.wait(timeout_seconds)
        return self.is_initialized()

    def is_initialized(self):
        """
        Checks whether the monitor was initialized.

        Returns:
            bool: True when monitor initialization succeeded.
        """
        return self._initialized_event.is_set()

    def is_stopping(self):
        """
        Checks whether a stop request was received.

        Returns:
            bool: True when shutdown was requested.
        """
        return self._stop_event.is_set()

    def has_failed(self):
        """
        Checks whether the monitor failed due to an exception.

        Returns:
            bool: True when an exception was registered.
        """
        return self._failed_event.is_set()

    def get_failure_state(self):
        """
        Retrieves the current monitor failure state.

        Returns:
            dict: Current failure status and failure details.
        """
        return {
            "failed": self.has_failed(),
            "critical": self.is_critical(),
            "failure_type": self._failure_type,
            "failure_message": self._failure_message
        }

    def get_monitor_name(self):
        """
        Returns the logical monitor name used for external logs.

        Returns:
            str: Logical monitor name.
        """
        return self._get_monitor_name()

    def _get_monitor_name(self):
        """
        Returns the logical monitor name used for diagnostics.

        Returns:
            str: Logical monitor name without thread-specific suffixes.
        """
        return (
            self.name
            .replace("Thread", "")
            .replace("Monitor", "")
        )

    def _register_failure(self, error):
        """
        Registers an unexpected monitor failure.
        """
        self._failed_event.set()
        self._failure_type = error.__class__.__name__
        self._failure_message = str(error)

    def _notify_failure_handler(self, error):
        """
        Notifies the configured failure handler when appropriate.
        """
        if not self._critical_failure:
            return

        if self._failure_handler is None:
            return

        self._failure_handler(self, error)

    def on_initialize(self):
        """
        Executes optional monitor-specific initialization logic.

        Returns:
            None: The base hook performs no initialization.
        """
        return None

    def on_cycle(self):
        """
        Executes a monitor-specific cycle.

        Raises:
            NotImplementedError: Always raised by the base implementation.
        """
        raise NotImplementedError

    def on_finalize(self):
        """
        Executes optional monitor-specific finalization logic.

        Returns:
            None: The base hook performs no finalization.
        """
        return None
