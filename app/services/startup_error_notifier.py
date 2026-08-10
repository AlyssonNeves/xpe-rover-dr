#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service for fatal startup configuration notifications."""


class StartupErrorNotifier(object):
    """Builds and delegates operator-visible startup error notifications."""

    MAX_COLUMNS = 22
    MAX_ROWS = 9

    def __init__(self, operator_alert_port):
        """Initializes the notifier with an operator alert output port."""
        self.operator_alert_port = operator_alert_port

    @classmethod
    def _screen_lines(cls, message):
        """Builds short lines that fit the EV3 text console."""
        lines = ["ROVER DR", "STARTUP ERROR"]

        token_names = []
        for token_name in (
                "ROVER_SHUTDOWN_TOKEN",
                "ROVER_HARDWARE_API_TOKEN"):
            if token_name in message:
                token_names.append(token_name.replace("ROVER_", ""))

        if token_names:
            lines.append("Missing config:")
            lines.extend(token_names)
        else:
            words = str(message).split()
            current = ""

            for word in words:
                candidate = word if not current else current + " " + word

                if len(candidate) <= cls.MAX_COLUMNS:
                    current = candidate
                else:
                    if current:
                        lines.append(current)

                    current = word[:cls.MAX_COLUMNS]

            if current:
                lines.append(current)

        lines.append("See README.md")
        lines.append("")
        lines.append("Press any button")
        lines.append("to finish")

        return lines[:cls.MAX_ROWS]

    def show(self, message):
        """Delegates a formatted fatal startup error to the output port."""
        return self.operator_alert_port.show_fatal_error(
            self._screen_lines(message)
        )
