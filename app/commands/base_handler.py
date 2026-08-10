#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared command-handler primitives for Rover application commands."""


class DomainCommandHandler(object):
    """Binds a command target to one application-level executor."""

    def __init__(self, target, executor):
        self.target = target
        self._executor = executor

    def handle(self, action, params):
        return self._executor(action, params)


class CommandHandlerRegistry(object):
    """Deterministic lookup of one handler per command target."""

    def __init__(self, handlers):
        self._handlers = {}
        for handler in handlers:
            if handler.target in self._handlers:
                raise ValueError(
                    "Duplicate command handler for target: {0}".format(
                        handler.target
                    )
                )
            self._handlers[handler.target] = handler

    def get(self, target):
        return self._handlers.get(target)

    def targets(self):
        return tuple(sorted(self._handlers.keys()))
