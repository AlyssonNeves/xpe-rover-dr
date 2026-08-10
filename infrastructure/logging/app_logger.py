#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple application logging service.

This module is responsible for providing centralized logging utilities
for application status and error messages.
"""

import sys
import threading

from datetime import datetime


class AppLogger(object):
    """Provides centralized application logging functionality."""

    @staticmethod
    def _timestamp():
        """
        Returns the current formatted date and time.

        Returns:
            str: Current timestamp formatted for log output.
        """
        return datetime.now().strftime("%d/%m/%y %H:%M:%S.%f")[:-3]

    @staticmethod
    def _thread_name():
        """
        Returns the current thread name.

        Returns:
            str: Name of the current execution thread.
        """
        return threading.current_thread().name

    @classmethod
    def status(cls, message):
        """
        Logs a status message.

        Args:
            message: Status message to be written to the log output.
        """
        print(
            "{} [STATUS][{:<23}] {}".format(
                cls._timestamp(),
                cls._thread_name(),
                message
            ),
            file=sys.stderr
        )

    @classmethod
    def warning(cls, message):
        """
        Logs a warning message.

        Args:
            message: Warning message to be written to the log output.
        """
        print(
            "{} [WARN  ][{:<23}] {}".format(
                cls._timestamp(),
                cls._thread_name(),
                message
            ),
            file=sys.stderr
        )

    @classmethod
    def error(cls, message):
        """
        Logs an error message.

        Args:
            message: Error message to be written to the log output.
        """
        print(
            "{} [ERROR ][{:<23}] {}".format(
                cls._timestamp(),
                cls._thread_name(),
                message
            ),
            file=sys.stderr
        )
