#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses


class StateCommandHandler(BaseCommandHandler):
    """Dispatches consolidated-state queries using only the query port."""

    def __init__(self, rover_state_query_port):
        self.rover_state_query_port = rover_state_query_port

    def execute(self, action, params):
        del params
        if self.rover_state_query_port is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.UNAVAILABLE,
                error="Rover state query port is not configured"
            )
        if action == CommandActions.READ_ROVER_STATE:
            return CommandResult(
                success=True,
                data=self.rover_state_query_port.get_rover_state()
            )
        return self.unsupported("state", action)

