#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Lifecycle and diagnostics contract for monitor components."""

from abc import ABCMeta, abstractmethod


class MonitorLifecyclePort(object, metaclass=ABCMeta):
    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @abstractmethod
    def join(self, timeout=None):
        raise NotImplementedError

    @abstractmethod
    def is_alive(self):
        raise NotImplementedError

    @abstractmethod
    def prepare_for_shutdown(self):
        raise NotImplementedError
