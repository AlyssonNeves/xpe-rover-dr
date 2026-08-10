#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for startup error notification orchestration."""

import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from app.services.startup_error_notifier import StartupErrorNotifier


class StartupErrorNotifierTestCase(unittest.TestCase):
    """Covers application-level startup error notifications."""

    def test_screen_lines_identify_missing_tokens(self):
        message = (
            "Missing required security configuration: "
            "ROVER_SHUTDOWN_TOKEN, ROVER_HARDWARE_API_TOKEN."
        )
        lines = StartupErrorNotifier._screen_lines(message)
        self.assertEqual(
            [
                "Missing tokens:",
                "SHUTDOWN",
                "HARDWARE API",
                StartupErrorNotifier.FOOTER_TEXT
            ],
            lines
        )

    def test_screen_lines_wrap_generic_messages(self):
        lines = StartupErrorNotifier._screen_lines(
            "A generic configuration error that must wrap safely"
        )
        self.assertLessEqual(
            len(lines) - 1,
            StartupErrorNotifier.MAX_MAIN_ROWS
        )
        self.assertTrue(all(
            len(line) <= StartupErrorNotifier.MAX_COLUMNS
            for line in lines[:-1]
        ))
        self.assertEqual(StartupErrorNotifier.FOOTER_TEXT, lines[-1])

    def test_show_delegates_formatted_lines_to_operator_alert_port(self):
        operator_alert_port = mock.Mock()
        operator_alert_port.show_fatal_error.return_value = True
        notifier = StartupErrorNotifier(operator_alert_port)

        shown = notifier.show("ROVER_SHUTDOWN_TOKEN")

        self.assertTrue(shown)
        operator_alert_port.show_fatal_error.assert_called_once_with(
            StartupErrorNotifier._screen_lines("ROVER_SHUTDOWN_TOKEN")
        )

    def test_show_propagates_adapter_unavailable_result(self):
        operator_alert_port = mock.Mock()
        operator_alert_port.show_fatal_error.return_value = False
        notifier = StartupErrorNotifier(operator_alert_port)

        self.assertFalse(notifier.show("configuration error"))


if __name__ == "__main__":
    unittest.main()
