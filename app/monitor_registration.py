#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Explicit monitor lifecycle and safety registration model."""


class MonitorRegistration(object):
    """Binds one monitor component to an explicit safety policy."""

    def __init__(self, component, name, critical=False):
        if component is None:
            raise ValueError("Monitor component is required.")
        if not name:
            raise ValueError("Monitor registration name is required.")
        self.component = component
        self.name = str(name)
        self.critical = bool(critical)
