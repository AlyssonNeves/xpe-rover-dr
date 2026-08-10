#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for selecting LOCAL Front, Drive and drive-detail parameters."""

from abc import ABCMeta, abstractmethod


class LocalDriveSetupSelectorPort(object, metaclass=ABCMeta):
    """Defines the operator-facing local drive setup contract."""

    @abstractmethod
    def select_setup(self, front, drive, centric, differential_mode=None):
        """Returns the selected local-drive setup or ``None`` on cancel."""
        raise NotImplementedError
