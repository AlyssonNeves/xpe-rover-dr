#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application-facing contract for the guarded EV3Dev2 motor domain."""

from abc import ABCMeta, abstractmethod


class MotorGatewayPort(object, metaclass=ABCMeta):
    """Defines the explicit gateway operations exposed to input adapters."""

    @abstractmethod
    def catalog(self):
        raise NotImplementedError

    @abstractmethod
    def create(self, class_name, args=None, kwargs=None, object_id=None):
        raise NotImplementedError

    @abstractmethod
    def list_objects(self):
        raise NotImplementedError

    @abstractmethod
    def list_operations(self):
        raise NotImplementedError

    @abstractmethod
    def delete(self, object_id):
        raise NotImplementedError

    @abstractmethod
    def invoke(self, object_id, method_name, args=None, kwargs=None):
        raise NotImplementedError

    @abstractmethod
    def get_property(self, object_id, property_name):
        raise NotImplementedError

    @abstractmethod
    def set_property(self, object_id, property_name, value):
        raise NotImplementedError

    @abstractmethod
    def module_value(self, member_name):
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError
