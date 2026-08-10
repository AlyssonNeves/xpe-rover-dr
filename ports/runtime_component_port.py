#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Lifecycle contract for assembled runtime components."""

from abc import ABCMeta, abstractmethod


class RuntimeComponentPort(object, metaclass=ABCMeta):
    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError
