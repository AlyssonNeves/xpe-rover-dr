#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output contract for operator-visible startup progress."""

from abc import ABCMeta, abstractmethod


class StartupProgressPort(object, metaclass=ABCMeta):
    """Presents the current control-initialization step to the operator."""

    @abstractmethod
    def show_startup_progress(self, message):
        """Shows one human-readable initialization progress message."""
        raise NotImplementedError

    def show_startup_error(self, message):
        """Shows a recoverable startup error using the normal presentation."""
        self.show_startup_progress(message)
