#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for guarded native EV3Dev2 motor gateway operations."""

from abc import ABCMeta, abstractmethod


class MotorGatewayPort(object, metaclass=ABCMeta):
    @abstractmethod
    def catalog(self): raise NotImplementedError
    @abstractmethod
    def create(self, class_name, args=None, kwargs=None, object_id=None):
        raise NotImplementedError
    @abstractmethod
    def list_objects(self): raise NotImplementedError
    @abstractmethod
    def list_operations(self): raise NotImplementedError
    @abstractmethod
    def delete(self, object_id): raise NotImplementedError
    @abstractmethod
    def invoke(self, object_id, method_name, args=None, kwargs=None):
        raise NotImplementedError
    @abstractmethod
    def get_property(self, object_id, property_name): raise NotImplementedError
    @abstractmethod
    def set_property(self, object_id, property_name, value):
        raise NotImplementedError
    @abstractmethod
    def module_value(self, name): raise NotImplementedError
