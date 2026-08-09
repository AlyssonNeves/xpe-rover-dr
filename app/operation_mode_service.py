#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service for Rover command and operation mode selection."""


class CommandModes(object):
    """Supported command-origin modes."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"

    @classmethod
    def values(cls):
        """Returns all supported command modes."""
        return (cls.LOCAL, cls.REMOTE)


class OperationModes(object):
    """Supported Rover execution modes."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"

    @classmethod
    def values(cls):
        """Returns all supported operation modes."""
        return (cls.MANUAL, cls.AUTOMATIC)


class OperationModeService(object):
    """Stores and validates the Rover operating-mode selection."""

    def __init__(
            self,
            selector_port=None,
            command_mode=CommandModes.LOCAL,
            operation_mode=OperationModes.MANUAL):
        self.selector_port = selector_port
        self._command_mode = self._validate_command_mode(command_mode)
        self._operation_mode = self._validate_operation_mode(operation_mode)

    def select(self):
        """Requests an operator selection through the configured output port."""
        if self.selector_port is None:
            return self.get_mode()

        selected = self.selector_port.select_mode(
            self._command_mode,
            self._operation_mode
        )

        if selected is None:
            return None

        self.set_mode(
            selected.get("command_mode"),
            selected.get("operation_mode")
        )
        return self.get_mode()

    def set_mode(self, command_mode, operation_mode):
        """Updates the current operating mode after validation."""
        self._command_mode = self._validate_command_mode(command_mode)
        self._operation_mode = self._validate_operation_mode(operation_mode)

    def get_mode(self):
        """Returns a defensive snapshot of the active operating mode."""
        return {
            "command_mode": self._command_mode,
            "operation_mode": self._operation_mode
        }

    @staticmethod
    def _validate_command_mode(value):
        if value not in CommandModes.values():
            raise ValueError("Unsupported command mode: {0}".format(value))
        return value

    @staticmethod
    def _validate_operation_mode(value):
        if value not in OperationModes.values():
            raise ValueError("Unsupported operation mode: {0}".format(value))
        return value
