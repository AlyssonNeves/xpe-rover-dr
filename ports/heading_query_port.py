#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only port for the latest cached Rover heading."""

from abc import ABCMeta, abstractmethod


class HeadingQueryPort(object, metaclass=ABCMeta):
    """Defines non-blocking access to a monitored heading snapshot."""

    @abstractmethod
    def get_heading_deg(self):
        """Returns a fresh heading in degrees or ``None`` when unavailable."""
        raise NotImplementedError

    @abstractmethod
    def get_heading_snapshot(self):
        """Returns a defensive snapshot including freshness information."""
        raise NotImplementedError
