#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Outbound adapter for consolidated Rover state queries."""

from ports.rover_state_query_port import RoverStateQueryPort


class RoverStateQueryAdapter(RoverStateQueryPort):
    """Delegates state queries to RoverStateService."""

    def __init__(self, rover_state_service):
        self.rover_state_service = rover_state_service

    def get_rover_state(self):
        return self.rover_state_service.get_rover_state()
