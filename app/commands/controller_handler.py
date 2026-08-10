#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses


class ControllerCommandHandler(BaseCommandHandler):
    """Dispatches controller queries using only the controller port."""

    def __init__(self, controller_port):
        self.controller_port = controller_port

    def execute(self, action, params):
        del params
        if self.controller_port is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.UNAVAILABLE,
                error="Controller port is not configured"
            )
        actions = {
            CommandActions.READ_CONTROLLER_STATUS: (
                self.controller_port.read_controller_status, "status"
            ),
            CommandActions.READ_CONTROLLER_NETWORK: (
                self.controller_port.read_network_status, "network"
            ),
            CommandActions.READ_CONTROLLER_BATTERY: (
                self.controller_port.read_battery_status, "battery"
            ),
            CommandActions.READ_CONTROLLER_SYSTEM: (
                self.controller_port.read_system_status, "system"
            ),
        }
        operation = actions.get(action)
        if operation is None:
            return self.unsupported("controller", action)
        reader, code = operation
        return self._success_or_not_found(
            reader(), "Controller", code
        )

