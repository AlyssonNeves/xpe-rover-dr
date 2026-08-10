#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared thread infrastructure for Rover-DR monitoring services."""

import threading
import time


class MonitorBase(threading.Thread):
    """Base class for simple periodic monitors."""

    def __init__(self, name, interval_seconds=1.0):
        threading.Thread.__init__(self, name="{}Thread".format(name))
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self.daemon = True

    def run(self):
        """Runs initialization followed by periodic monitoring cycles."""
        self.on_initialize()
        try:
            while not self._stop_event.is_set():
                self.on_cycle()
                self._stop_event.wait(self.interval_seconds)
        finally:
            self.on_finalize()

    def stop(self):
        """Requests monitor shutdown."""
        self._stop_event.set()

    def is_stopping(self):
        """Returns True when shutdown has been requested."""
        return self._stop_event.is_set()

    def on_initialize(self):
        """Hook executed before the first cycle."""
        return None

    def on_cycle(self):
        """Hook executed once per monitoring cycle."""
        raise NotImplementedError

    def on_finalize(self):
        """Hook executed when the monitoring loop finishes."""
        return None
