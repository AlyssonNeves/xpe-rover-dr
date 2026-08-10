#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Process lifecycle output port."""

from abc import ABCMeta, abstractmethod


class ProcessControlPort(object, metaclass=ABCMeta):
    @abstractmethod
    def restart_current_process(self):
        raise NotImplementedError
