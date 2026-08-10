#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared command-result helpers."""

from app.models import CommandResult, ResultStatuses

INTEGER_TYPES = (int,)


class BaseCommandHandler(object):
    @staticmethod
    def unsupported(domain, action):
        return CommandResult(
            success=False,
            status=ResultStatuses.INVALID_ARGUMENT,
            error="Unsupported {} action: {}".format(domain, action)
        )

    @staticmethod
    def _success_or_not_found(data, resource_name, code):
        if data is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.NOT_FOUND,
                error="{} not found: {}".format(resource_name, code)
            )
        return CommandResult(success=True, data=data)

    @staticmethod
    def _is_integer(value):
        return isinstance(value, INTEGER_TYPES) and not isinstance(value, bool)
