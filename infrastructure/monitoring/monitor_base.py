#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared lifecycle, diagnostics and failure policy for Rover monitors."""

import threading

from infrastructure.logging.app_logger import AppLogger


class MonitorBase(threading.Thread):
    """Base implementation for periodic monitor components."""

    def __init__(self, name, interval_seconds=1.0):
        threading.Thread.__init__(self, name="{}Thread".format(name))
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._initialized_event = threading.Event()
        self._initialization_completed_event = threading.Event()
        self._failed_event = threading.Event()
        self._failure_type = None
        self._failure_message = None
        self._critical_failure = False
        self._failure_handler = None
        self.daemon = True

    def run(self):
        """Runs initialization followed by periodic monitoring cycles."""
        AppLogger.status(
            "{} Monitor initializing.".format(self.get_monitor_name())
        )
        try:
            self.on_initialize()
            self._initialized_event.set()
            self._initialization_completed_event.set()
            AppLogger.status(
                "{} Monitor initialized.".format(self.get_monitor_name())
            )
            while not self._stop_event.is_set():
                self.on_cycle()
                self._stop_event.wait(self.interval_seconds)
        except Exception as error:
            self._register_failure(error)
            self._initialization_completed_event.set()
            AppLogger.error(
                "Error in {} Monitor: {}".format(
                    self.get_monitor_name(), error
                )
            )
            self._notify_failure_handler(error)
        finally:
            try:
                self.on_finalize()
            except Exception as error:
                AppLogger.error(
                    "Unexpected error finalizing {} Monitor: {}".format(
                        self.get_monitor_name(), error
                    )
                )
            AppLogger.status(
                "{} Monitor finalized.".format(self.get_monitor_name())
            )

    def stop(self):
        self._stop_event.set()

    def prepare_for_shutdown(self):
        """Hook for safety actions that must precede a monitor stop."""
        return None

    def set_failure_policy(self, critical=False, failure_handler=None):
        self._critical_failure = bool(critical)
        self._failure_handler = failure_handler

    def is_critical(self):
        return self._critical_failure

    def wait_until_initialized(self, timeout_seconds=None):
        self._initialization_completed_event.wait(timeout_seconds)
        return self.is_initialized()

    def is_initialized(self):
        return self._initialized_event.is_set()

    def is_stopping(self):
        return self._stop_event.is_set()

    def has_failed(self):
        return self._failed_event.is_set()

    def get_failure_state(self):
        return {
            "failed": self.has_failed(),
            "critical": self.is_critical(),
            "failure_type": self._failure_type,
            "failure_message": self._failure_message
        }

    def get_monitor_name(self):
        return self.name.replace("Thread", "").replace("Monitor", "")

    def _register_failure(self, error):
        self._failed_event.set()
        self._failure_type = error.__class__.__name__
        self._failure_message = str(error)

    def _notify_failure_handler(self, error):
        if self._critical_failure and self._failure_handler is not None:
            self._failure_handler(self, error)

    def on_initialize(self):
        return None

    def on_cycle(self):
        raise NotImplementedError

    def on_finalize(self):
        return None
