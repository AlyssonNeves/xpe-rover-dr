#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Explicit application command handlers grouped by domain target.

The handlers keep the application dispatch independent from HTTP routing.  At
this stage they delegate execution to the domain-specific operations already
implemented by ``CommandService``; later commits may evolve each handler
without changing the input adapters.
"""


class DomainCommandHandler(object):
    """Binds a command target to one application-level executor."""

    def __init__(self, target, executor):
        self.target = target
        self._executor = executor

    def handle(self, action, params):
        return self._executor(action, params)


class SensorCommandHandler(DomainCommandHandler):
    pass


class MotorCommandHandler(DomainCommandHandler):
    pass


class ControllerCommandHandler(DomainCommandHandler):
    pass


class RoverCommandHandler(DomainCommandHandler):
    pass


class DriveCommandHandler(DomainCommandHandler):
    pass


class CommandHandlerRegistry(object):
    """Immutable-by-convention lookup of handlers by command target."""

    def __init__(self, handlers):
        self._handlers = {}
        for handler in handlers:
            if handler.target in self._handlers:
                raise ValueError(
                    "Duplicate command handler for target: {}".format(
                        handler.target
                    )
                )
            self._handlers[handler.target] = handler

    def get(self, target):
        return self._handlers.get(target)

    def targets(self):
        return tuple(sorted(self._handlers.keys()))
