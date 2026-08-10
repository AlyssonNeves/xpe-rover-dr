#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Query contract for monitor diagnostics exposed to application services."""

from abc import ABCMeta, abstractmethod


class MonitorDiagnosticsPort(object, metaclass=ABCMeta):
    """Defines the explicit diagnostic snapshot contract for monitors."""

    @abstractmethod
    def get_failure_state(self):
        raise NotImplementedError
