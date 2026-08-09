#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for operator-visible fatal alerts."""

from abc import ABCMeta, abstractmethod


class OperatorAlertPort(object, metaclass=ABCMeta):
    """Defines the contract for presenting a fatal alert to an operator."""

    @abstractmethod
    def show_fatal_error(self, lines):
        """Displays a fatal error and waits for operator acknowledgement."""
        raise NotImplementedError
