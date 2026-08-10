#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application lifecycle coordinator for Rover-DR."""

import threading

from app.rover_config import SHUTDOWN_JOIN_TIMEOUT_SECONDS
from services.app_logger import AppLogger


class RoverApplication(object):
    """Coordinates startup, execution and orderly shutdown of the application."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"

    def __init__(self, monitors, rest_api, managed_services=None):
        self.monitors = list(monitors)
        self.rest_api = rest_api
        self.managed_services = list(managed_services or [])
        self._status = self.CREATED
        self._status_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._restart_requested = False
        self._stopped_event = threading.Event()
        self._rest_thread = None

    def get_status(self):
        """Returns the current lifecycle status."""
        with self._status_lock:
            return self._status

    def _set_status(self, status):
        with self._status_lock:
            self._status = status

    def start(self):
        """Starts monitors and the REST input adapter."""
        if self.get_status() != self.CREATED:
            return

        self._stopped_event.clear()
        self._set_status(self.STARTING)
        AppLogger.status("Starting Rover-DR application.")

        for monitor in self.monitors:
            monitor.start()
            AppLogger.status("Started {}.".format(monitor.name))

        for service in self.managed_services:
            start = getattr(service, "start", None)
            if callable(start):
                start()
                AppLogger.status(
                    "Started managed service {}.".format(
                        service.__class__.__name__
                    )
                )

        self._rest_thread = threading.Thread(
            target=self.rest_api.start,
            name="RestApiThread"
        )
        self._rest_thread.daemon = True
        self._rest_thread.start()

        self._set_status(self.RUNNING)
        AppLogger.status("Rover-DR application is running.")

    def stop(self):
        """Stops the REST adapter and all monitoring threads in order."""
        status = self.get_status()
        if status in (self.STOPPING, self.STOPPED):
            return

        self._set_status(self.STOPPING)
        AppLogger.status("Stopping Rover-DR application.")

        self.rest_api.stop()

        for monitor in self.monitors:
            monitor.stop()

        for monitor in self.monitors:
            if monitor.is_alive():
                monitor.join(SHUTDOWN_JOIN_TIMEOUT_SECONDS)

        for service in self.managed_services:
            close = getattr(service, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as error:
                    AppLogger.error(
                        "Error while closing managed service {}: {}".format(
                            service.__class__.__name__, error
                        )
                    )

        if self._rest_thread is not None and self._rest_thread.is_alive():
            self._rest_thread.join(SHUTDOWN_JOIN_TIMEOUT_SECONDS)

        self._set_status(self.STOPPED)
        self._stopped_event.set()
        AppLogger.status("Rover-DR application stopped.")

    def restart(self):
        """Requests an orderly application restart after shutdown."""
        with self._restart_lock:
            self._restart_requested = True
        AppLogger.status("Remote Rover-DR restart requested.")
        self.stop()

    def is_restart_requested(self):
        """Returns whether a restart was requested through the lifecycle API."""
        with self._restart_lock:
            return self._restart_requested

    def wait(self):
        """Blocks the caller until application shutdown is completed."""
        self._stopped_event.wait()
