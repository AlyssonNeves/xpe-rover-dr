#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Reusable route matching primitives for the Rover REST adapter."""


class Route(object):
    """Describes an HTTP route and its handler name."""

    def __init__(self, method, pattern, handler_name):
        self.method = method.upper()
        self.pattern = tuple(pattern)
        self.handler_name = handler_name

    def match(self, method, path_parts):
        if method.upper() != self.method or len(path_parts) != len(self.pattern):
            return None
        params = {}
        for expected, actual in zip(self.pattern, path_parts):
            if expected.startswith("{") and expected.endswith("}"):
                params[expected[1:-1]] = actual
            elif expected != actual:
                return None
        return params


class RouteDispatcher(object):
    """Dispatches requests using a declarative route table."""

    def __init__(self, routes=None):
        self.routes = list(routes or [])

    def add(self, method, pattern, handler_name):
        self.routes.append(Route(method, pattern, handler_name))

    def resolve(self, method, path_parts):
        for route in self.routes:
            params = route.match(method, path_parts)
            if params is not None:
                return route.handler_name, params
        return None, None
