#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Minimal process entry point for the Rover application."""

import signal
import sys

from bootstrap.rover_assembly import (
    ApplicationStartupError, prepare_rover_runtime
)


runtime = None


def request_shutdown(signal_number=None, frame=None):
    """Delegates signal-safe shutdown scheduling to the runtime context."""
    del signal_number
    del frame
    if runtime is not None:
        runtime.request_shutdown()


def main():
    """Builds and executes the runtime prepared by the composition root."""
    global runtime
    runtime = prepare_rover_runtime()
    if not runtime.ready:
        return runtime.exit_code

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)

    runtime.logger.status("Runtime: Python {0}".format(sys.version.split()[0]))
    exit_code = 0
    try:
        runtime.start()
    except ApplicationStartupError as error:
        runtime.logger.error("Rover startup aborted: {0}".format(error))
        exit_code = 1
    except KeyboardInterrupt:
        request_shutdown()
    finally:
        runtime.stop_or_join()
        runtime.finish()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
