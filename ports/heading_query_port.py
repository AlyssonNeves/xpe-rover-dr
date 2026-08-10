#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only port for the latest monitored heading."""

from abc import ABCMeta, abstractmethod


class HeadingQueryPort(object, metaclass=ABCMeta):
    """Defines non-blocking access to cached heading information."""

    @abstractmethod
    def get_heading_deg(self):
        """Returns a fresh heading value or ``None`` when unavailable."""
        raise NotImplementedError

    @abstractmethod
    def get_heading_snapshot(self):
        """Returns the latest defensive heading-state snapshot."""
        raise NotImplementedError
