#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service for Rover Command and Control selection."""


class Commands(object):
    """Supported command origins."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"

    @classmethod
    def values(cls):
        """Returns all supported Command values."""
        return (cls.LOCAL, cls.REMOTE)


class Controls(object):
    """Supported local control strategies."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"

    @classmethod
    def values(cls):
        """Returns all supported Control values."""
        return (cls.MANUAL, cls.AUTOMATIC)


class OperationModeService(object):
    """Stores and validates the selected Rover Command and Control values."""

    def __init__(
            self,
            command_control_selector_port=None,
            command=Commands.LOCAL,
            control=Controls.MANUAL):
        self.command_control_selector_port = command_control_selector_port
        self._local_control = self._validate_control(control)
        self._command = self._validate_command(command)
        self._control = (
            self._local_control if self._command == Commands.LOCAL else None
        )

    def select_command_control(self):
        """Requests Command/Control selection through the configured port."""
        if self.command_control_selector_port is None:
            return self.get_mode()

        selected = self.command_control_selector_port.select_mode(
            self._command,
            self._control or self._local_control
        )
        if selected is None:
            return None

        self.set_command_control(
            selected.get("command"),
            selected.get("control")
        )
        return self.get_mode()

    def set_command_control(self, command, control=None):
        """Updates Command/Control while enforcing their applicability."""
        command = self._validate_command(command)
        if command == Commands.REMOTE:
            self._command = command
            self._control = None
            return

        if control is None:
            control = self._local_control
        self._local_control = self._validate_control(control)
        self._command = command
        self._control = self._local_control

    def get_mode(self):
        """Returns a defensive snapshot of the active Command/Control pair."""
        return {
            "command": self._command,
            "control": self._control
        }

    @staticmethod
    def _validate_command(value):
        if value not in Commands.values():
            raise ValueError("Unsupported Rover command: {0}".format(value))
        return value

    @staticmethod
    def _validate_control(value):
        if value not in Controls.values():
            raise ValueError("Unsupported Rover control: {0}".format(value))
        return value
