#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Independent high-resolution motor safety watchdog."""

import threading


class MotorSafetyWatchdog(object):
    """Runs a deadline evaluator independently from telemetry polling."""

    def __init__(self, evaluator, logger, interval_seconds=0.05):
        self._evaluator = evaluator
        self._logger = logger
        self._interval_seconds = float(interval_seconds)
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="MotorWatchdogThread"
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self, timeout_seconds=0.5):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)

    def _run(self):
        while not self._stop_event.wait(self._interval_seconds):
            try:
                self._evaluator()
            except Exception as error:
                self._logger.error(
                    "Motor watchdog evaluation failed: {0}".format(error)
                )
