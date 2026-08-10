#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for S02.13 EV3 PBM cache startup integration."""

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from bootstrap import rover_assembly


def test_prepare_ev3_screen_cache_logs_loaded_assets():
    result = {
        "total": 15,
        "memory_hits": 0,
        "loaded": 15,
        "failed": []
    }
    with mock.patch.object(
            rover_assembly,
            "warm_monochrome_screen_cache",
            return_value=result) as warmer, \
            mock.patch.object(rover_assembly.AppLogger, "status") as status, \
            mock.patch.object(rover_assembly.AppLogger, "warning") as warning:
        returned = rover_assembly._prepare_ev3_screen_cache()

    assert result == returned
    warmer.assert_called_once_with()
    assert status.call_count == 1
    warning.assert_not_called()


def test_prepare_ev3_screen_cache_warns_but_does_not_abort_on_bad_asset():
    result = {
        "total": 15,
        "memory_hits": 0,
        "loaded": 14,
        "failed": [("Broken.pbm", "invalid PBM")]
    }
    with mock.patch.object(
            rover_assembly,
            "warm_monochrome_screen_cache",
            return_value=result), \
            mock.patch.object(rover_assembly.AppLogger, "status"), \
            mock.patch.object(rover_assembly.AppLogger, "warning") as warning:
        returned = rover_assembly._prepare_ev3_screen_cache()

    assert result == returned
    warning.assert_called_once()


def test_prepare_rover_application_warms_cache_before_mode_selection():
    call_order = []
    mode_service = mock.Mock()
    application = object()

    with mock.patch.object(rover_assembly.rover_config, "HARDWARE_ENABLED", True), \
            mock.patch.object(
                rover_assembly,
                "validate_startup_configuration",
                side_effect=lambda: call_order.append("validate") or True), \
            mock.patch.object(
                rover_assembly,
                "_prepare_ev3_screen_cache",
                side_effect=lambda: call_order.append("warm") or {}), \
            mock.patch.object(
                rover_assembly,
                "select_operation_mode",
                side_effect=lambda: call_order.append("select") or mode_service), \
            mock.patch.object(
                rover_assembly,
                "build_rover_application",
                return_value=application) as build:
        returned = rover_assembly.prepare_rover_application()

    assert application is returned
    assert ["validate", "warm", "select"] == call_order
    build.assert_called_once_with(operation_mode_service=mode_service)
