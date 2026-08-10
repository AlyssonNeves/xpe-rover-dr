#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Concurrency boundary used by the application lifecycle coordinator."""

from abc import ABCMeta, abstractmethod


class ApplicationConcurrencyPort(object, metaclass=ABCMeta):
    @abstractmethod
    def claim_stop(self):
        raise NotImplementedError

    @abstractmethod
    def is_stop_requested(self):
        raise NotImplementedError

    @abstractmethod
    def wait_for_stop_completed(self, timeout_seconds):
        raise NotImplementedError

    @abstractmethod
    def mark_stop_completed(self):
        raise NotImplementedError

    @abstractmethod
    def claim_shutdown_request(self):
        raise NotImplementedError

    @abstractmethod
    def claim_restart_request(self):
        raise NotImplementedError

    @abstractmethod
    def is_restart_requested(self):
        raise NotImplementedError

    @abstractmethod
    def claim_critical_shutdown(self):
        raise NotImplementedError

    @abstractmethod
    def run_async(self, target, name, daemon):
        raise NotImplementedError

    @abstractmethod
    def is_current_component(self, component):
        raise NotImplementedError
