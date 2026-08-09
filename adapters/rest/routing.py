#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Small routing primitives shared by Rover-DR REST command routes."""

from app.models import CommandResult


class GatewayRouter(object):
    """Translates gateway calls into application ``CommandResult`` objects."""

    def __init__(self, gateway):
        self.gateway = gateway

    def call(self, method_name, *args):
        if self.gateway is None:
            return CommandResult.service_unavailable(
                "ev3dev2.motor gateway is unavailable"
            )
        try:
            method = getattr(self.gateway, method_name)
            return CommandResult.ok(method(*args))
        except Exception as exc:
            return CommandResult.bad_request(str(exc))


def parse_command_id(value):
    """Returns an integer command id when possible, preserving legacy ids."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
