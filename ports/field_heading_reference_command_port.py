#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Command port for redefining the operational FIELD heading reference."""

from abc import ABCMeta, abstractmethod


class FieldHeadingReferenceCommandPort(object, metaclass=ABCMeta):
    """Defines safe runtime changes to the FIELD zero reference."""

    @abstractmethod
    def set_current_heading_as_zero(self):
        """Uses the latest fresh canonical heading as the FIELD zero."""
        raise NotImplementedError
