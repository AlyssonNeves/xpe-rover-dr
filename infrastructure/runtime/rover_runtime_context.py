#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Runtime context returned by the composition root to the entry point."""


class RoverRuntimeContext(object):
    """Owns entry-point lifecycle details without runtime synchronization."""

    def __init__(self, application=None, logger=None, exit_code=0):
        self.application = application
        self.logger = logger
        self.exit_code = int(exit_code)

    @property
    def ready(self):
        return self.application is not None and self.exit_code == 0

    def start(self):
        self.application.start()

    def request_shutdown(self):
        if self.application is not None:
            self.application.request_shutdown()

    def stop_or_join(self):
        if self.application is not None:
            self.application.stop()

    def finish(self):
        if self.logger is not None:
            self.logger.status("Rover application finished.")
