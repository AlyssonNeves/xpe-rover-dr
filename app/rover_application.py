#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application lifecycle coordinator for Rover-DR."""

import threading

from services.app_logger import AppLogger


class RoverApplication(object):
    """Coordinates startup, execution and orderly shutdown of the application."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"

    def __init__(self, monitors, rest_api):
        self.monitors = list(monitors)
        self.rest_api = rest_api
        self._status = self.CREATED
        self._status_lock = threading.Lock()
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
                monitor.join(2.0)

        if self._rest_thread is not None and self._rest_thread.is_alive():
            self._rest_thread.join(2.0)

        self._set_status(self.STOPPED)
        self._stopped_event.set()
        AppLogger.status("Rover-DR application stopped.")

    def wait(self):
        """Blocks the caller until application shutdown is completed."""
        self._stopped_event.wait()
