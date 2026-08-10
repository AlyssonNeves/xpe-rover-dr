#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Minimal process entry point; concrete assembly lives in bootstrap."""

import os
import signal
import sys

from bootstrap import rover_assembly


application = None


def request_shutdown(signum=None, _frame=None):
    """Delegates process signals to the already assembled application."""
    if application is not None:
        rover_assembly.AppLogger.status(
            "Shutdown requested by signal {0}.".format(signum)
        )
        application.stop()


def main():
    """Prepares, starts and terminates the Rover process."""
    global application
    application = rover_assembly.prepare_rover_application()
    if application is None:
        return 1

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)

    try:
        application.start()
        application.wait()
    except KeyboardInterrupt:
        application.stop()
    finally:
        application.stop()

    if application.is_restart_requested():
        rover_assembly.AppLogger.status("Restarting Rover-DR process.")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
