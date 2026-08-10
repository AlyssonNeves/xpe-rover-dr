#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Canonical Rover operation-mode model and selection service."""


class Commands(object):
    """Supported command origins."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"

    @classmethod
    def values(cls):
        return (cls.LOCAL, cls.REMOTE)


class Controls(object):
    """Supported local control strategies."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"

    @classmethod
    def values(cls):
        return (cls.MANUAL, cls.AUTOMATIC)


class Fronts(object):
    """Operator-facing Rover front conventions."""

    NOSE = "NOSE"
    TAIL = "TAIL"

    @classmethod
    def values(cls):
        return (cls.NOSE, cls.TAIL)


class Drives(object):
    """Supported traction arrangements."""

    DIFFERENTIAL = "DIFFERENTIAL"
    MECANUM = "MECANUM"

    @classmethod
    def values(cls):
        return (cls.DIFFERENTIAL, cls.MECANUM)


class Centrics(object):
    """Supported Mecanum reference frames."""

    CHASSIS = "CHASSIS"
    FIELD = "FIELD"

    @classmethod
    def values(cls):
        return (cls.CHASSIS, cls.FIELD)


class RoverOperationMode(object):
    """Validated, protocol-independent Rover operation-mode value object.

    Applicability is encoded directly in the structure:

    * REMOTE makes control/front/drive/centric not applicable (``None``).
    * LOCAL requires control, front and drive.
    * DIFFERENTIAL makes centric not applicable (``None``).
    * MECANUM requires CHASSIS or FIELD centricity.
    """

    __slots__ = ("_command", "_control", "_front", "_drive", "_centric")

    def __init__(self, command=Commands.LOCAL, control=Controls.MANUAL,
                 front=Fronts.NOSE, drive=Drives.DIFFERENTIAL,
                 centric=None):
        self._command = self._validate(command, Commands.values(), "command")

        if self._command == Commands.REMOTE:
            self._control = None
            self._front = None
            self._drive = None
            self._centric = None
            return

        self._control = self._validate(control, Controls.values(), "control")
        self._front = self._validate(front, Fronts.values(), "front")
        self._drive = self._validate(drive, Drives.values(), "drive")
        if self._drive == Drives.MECANUM:
            active_centric = centric or Centrics.CHASSIS
            self._centric = self._validate(
                active_centric, Centrics.values(), "centric"
            )
        else:
            self._centric = None

    @property
    def command(self):
        return self._command

    @property
    def control(self):
        return self._control

    @property
    def front(self):
        return self._front

    @property
    def drive(self):
        return self._drive

    @property
    def centric(self):
        return self._centric

    def is_local(self):
        return self._command == Commands.LOCAL

    def is_local_manual(self):
        return self.is_local() and self._control == Controls.MANUAL

    def to_dict(self):
        """Returns a defensive transport-friendly snapshot."""
        return {
            "command": self._command,
            "control": self._control,
            "front": self._front,
            "drive": self._drive,
            "centric": self._centric
        }

    @staticmethod
    def _validate(value, supported, field_name):
        if value not in supported:
            raise ValueError(
                "Unsupported Rover {0}: {1}".format(field_name, value)
            )
        return value


class OperationModeService(object):
    """Single source of truth for all selected Rover operation parameters."""

    def __init__(self, command_control_selector_port=None,
                 local_drive_selector_port=None,
                 command=Commands.LOCAL, control=Controls.MANUAL,
                 front=Fronts.NOSE, drive=Drives.DIFFERENTIAL,
                 centric=None):
        self.command_control_selector_port = command_control_selector_port
        self.local_drive_selector_port = local_drive_selector_port

        self._local_control = self._validate_control(control)
        self._local_front = self._validate_front(front)
        self._local_drive = self._validate_drive(drive)
        self._local_centric = self._validate_centric(
            centric or Centrics.CHASSIS
        )
        self._mode = RoverOperationMode(
            command=command,
            control=self._local_control,
            front=self._local_front,
            drive=self._local_drive,
            centric=self._local_centric
        )

    def select_command_control(self):
        """Requests Command/Control selection through the configured port."""
        if self.command_control_selector_port is None:
            return self.get_snapshot()

        selected = self.command_control_selector_port.select_mode(
            self._mode.command,
            self._mode.control or self._local_control
        )
        if selected is None:
            return None

        self.set_command_control(
            selected["command"], selected.get("control")
        )
        return self.get_snapshot()

    def select_local_drive(self):
        """Requests Front/Drive/Centric selection for a LOCAL command mode."""
        if not self._mode.is_local():
            raise RuntimeError(
                "Front, drive and centric selections require LOCAL command."
            )
        if self.local_drive_selector_port is None:
            return self.get_snapshot()

        selected = self.local_drive_selector_port.select_setup(
            self._mode.front,
            self._mode.drive,
            self._mode.centric or self._local_centric
        )
        if selected is None:
            return None

        self.set_local_drive(
            selected["front"], selected["drive"], selected.get("centric")
        )
        return self.get_snapshot()

    def set_command_control(self, command, control=None):
        """Updates Command/Control and applies all applicability invariants."""
        if command not in Commands.values():
            raise ValueError("Unsupported Rover command: {0}".format(command))
        if command == Commands.REMOTE:
            self._mode = RoverOperationMode(command=Commands.REMOTE)
            return

        if control is None:
            control = self._local_control
        self._local_control = self._validate_control(control)
        self._mode = RoverOperationMode(
            command=Commands.LOCAL,
            control=self._local_control,
            front=self._local_front,
            drive=self._local_drive,
            centric=self._local_centric
        )

    def set_local_drive(self, front, drive, centric=None):
        """Updates Front/Drive/Centric for the active LOCAL command mode."""
        if not self._mode.is_local():
            raise RuntimeError(
                "Front, drive and centric selections require LOCAL command."
            )
        self._local_front = self._validate_front(front)
        self._local_drive = self._validate_drive(drive)
        if self._local_drive == Drives.MECANUM:
            self._local_centric = self._validate_centric(centric)
        elif centric is not None:
            self._validate_centric(centric)

        self._mode = RoverOperationMode(
            command=Commands.LOCAL,
            control=self._local_control,
            front=self._local_front,
            drive=self._local_drive,
            centric=self._local_centric
        )

    def get_mode(self):
        """Returns the canonical immutable-by-contract value object."""
        return self._mode

    def get_snapshot(self):
        """Returns all five parameters in one defensive dictionary."""
        return self._mode.to_dict()

    @staticmethod
    def _validate_control(value):
        if value not in Controls.values():
            raise ValueError("Unsupported Rover control: {0}".format(value))
        return value

    @staticmethod
    def _validate_front(value):
        if value not in Fronts.values():
            raise ValueError("Unsupported Rover front: {0}".format(value))
        return value

    @staticmethod
    def _validate_drive(value):
        if value not in Drives.values():
            raise ValueError("Unsupported Rover drive: {0}".format(value))
        return value

    @staticmethod
    def _validate_centric(value):
        if value not in Centrics.values():
            raise ValueError("Unsupported Rover centric: {0}".format(value))
        return value


def coerce_operation_mode(value):
    """Converts canonical mode structures into one validated value object."""
    if isinstance(value, RoverOperationMode):
        return value
    if value is None:
        return RoverOperationMode()
    if hasattr(value, "get_mode"):
        return coerce_operation_mode(value.get_mode())
    if hasattr(value, "get_snapshot"):
        return coerce_operation_mode(value.get_snapshot())
    if not isinstance(value, dict):
        raise TypeError("Operation mode must be a service, value object or dict.")

    supported_fields = frozenset((
        "command", "control", "front", "drive", "centric"
    ))
    unsupported_fields = set(value) - supported_fields
    if unsupported_fields:
        raise ValueError(
            "Unsupported operation-mode fields: {0}".format(
                ", ".join(sorted(unsupported_fields))
            )
        )

    command = value.get("command", Commands.LOCAL)
    if command == Commands.REMOTE:
        return RoverOperationMode(command=Commands.REMOTE)
    return RoverOperationMode(
        command=command,
        control=value.get("control", Controls.MANUAL),
        front=value.get("front", Fronts.NOSE),
        drive=value.get("drive", Drives.DIFFERENTIAL),
        centric=value.get("centric")
    )
