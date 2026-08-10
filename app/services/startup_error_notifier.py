#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service for fatal startup configuration notifications."""


class StartupErrorNotifier(object):
    """Builds and delegates operator-visible startup error notifications."""

    MAX_COLUMNS = 16
    MAX_MAIN_ROWS = 3
    FOOTER_TEXT = "Press any button to finish"

    def __init__(self, operator_alert_port):
        """Initializes the notifier with an operator alert output port."""
        self.operator_alert_port = operator_alert_port

    @classmethod
    def _screen_lines(cls, message):
        """Builds a concise main message plus the fixed bottom instruction."""
        token_labels = []

        if "ROVER_SHUTDOWN_TOKEN" in message:
            token_labels.append("SHUTDOWN")
        if "ROVER_HARDWARE_API_TOKEN" in message:
            token_labels.append("HARDWARE API")

        if token_labels:
            main_lines = ["Missing tokens:"] + token_labels
        else:
            main_lines = cls._wrap_message(message)

        return main_lines[:cls.MAX_MAIN_ROWS] + [cls.FOOTER_TEXT]

    @classmethod
    def _wrap_message(cls, message):
        """Wraps a generic error into the available main-message rows."""
        lines = []
        current = ""

        for word in str(message).split():
            candidate = word if not current else current + " " + word

            if len(candidate) <= cls.MAX_COLUMNS:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word[:cls.MAX_COLUMNS]

            if len(lines) >= cls.MAX_MAIN_ROWS:
                break

        if current and len(lines) < cls.MAX_MAIN_ROWS:
            lines.append(current)

        return lines or ["Startup error"]

    def show(self, message):
        """Delegates a formatted fatal startup error to the output port."""
        return self.operator_alert_port.show_fatal_error(
            self._screen_lines(message)
        )
