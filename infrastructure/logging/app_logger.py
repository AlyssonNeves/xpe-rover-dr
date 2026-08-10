#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Centralized application logging for Rover-DR."""

import sys
import threading
from datetime import datetime


class AppLogger(object):
    """Provides small, consistent status and error log messages."""

    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%d/%m/%y %H:%M:%S.%f")[:-3]

    @staticmethod
    def _thread_name():
        return threading.current_thread().name

    @classmethod
    def _write(cls, level, message):
        print(
            "{} [{:<6}][{:<23}] {}".format(
                cls._timestamp(), level, cls._thread_name(), message
            ),
            file=sys.stderr
        )

    @classmethod
    def status(cls, message):
        """Writes an application status message."""
        cls._write("STATUS", message)

    @classmethod
    def warning(cls, message):
        """Writes an application warning message."""
        cls._write("WARN", message)

    @classmethod
    def error(cls, message):
        """Writes an application error message."""
        cls._write("ERROR", message)
