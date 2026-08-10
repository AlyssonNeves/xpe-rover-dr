#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Static coverage checks for the distributed Postman collection."""

import json
from pathlib import Path


COLLECTION_PATH = Path(__file__).parents[1] / "postman" / "rover_dr_rest_api_collection.json"


def _requests():
    collection = json.loads(COLLECTION_PATH.read_text())
    result = []

    def visit(items):
        for item in items:
            if "item" in item:
                visit(item["item"])
            elif "request" in item:
                request = item["request"]
                result.append((request.get("method"), request.get("url", {}).get("raw")))

    visit(collection["item"])
    return result


def test_postman_collection_covers_current_motor_and_drive_routes():
    routes = set(_requests())
    required = {
        ("GET", "{{baseUrl}}/api/motors"),
        ("GET", "{{baseUrl}}/api/motors/all"),
        ("GET", "{{baseUrl}}/api/motor-commands"),
        ("POST", "{{baseUrl}}/api/motors/LLM/stop"),
        ("POST", "{{baseUrl}}/api/motors/LLM/run-timed"),
        ("POST", "{{baseUrl}}/api/motors/LLM/run-forever"),
        ("POST", "{{baseUrl}}/api/motors/LLM/run-direct"),
        ("POST", "{{baseUrl}}/api/motors/LLM/run-to-rel-pos"),
        ("POST", "{{baseUrl}}/api/motors/LLM/run-to-abs-pos"),
        ("POST", "{{baseUrl}}/api/motors/LLM/cancel"),
        ("POST", "{{baseUrl}}/api/motors/LLM/reset"),
        ("POST", "{{baseUrl}}/api/motors/sync"),
        ("POST", "{{baseUrl}}/api/motors/stop-all"),
        ("GET", "{{baseUrl}}/api/drive/status"),
        ("GET", "{{baseUrl}}/api/drive/telemetry"),
        ("POST", "{{baseUrl}}/api/drive/tank"),
        ("POST", "{{baseUrl}}/api/drive/stop"),
        ("POST", "{{baseUrl}}/api/drive/move-distance"),
        ("POST", "{{baseUrl}}/api/drive/rotate-angle"),
        ("POST", "{{baseUrl}}/api/drive/curve-radius"),
        ("POST", "{{baseUrl}}/api/drive/odometry/reset"),
        ("POST", "{{baseUrl}}/api/drive/navigation-stop"),
    }
    assert required.issubset(routes), "Missing Postman routes: {}".format(sorted(required - routes))


def test_postman_collection_contains_run_direct_negative_validation():
    collection = json.loads(COLLECTION_PATH.read_text())
    payloads = []

    def visit(items):
        for item in items:
            if "item" in item:
                visit(item["item"])
            elif item.get("request", {}).get("body", {}).get("raw"):
                try:
                    payloads.append(json.loads(item["request"]["body"]["raw"]))
                except (TypeError, ValueError):
                    pass

    visit(collection["item"])
    assert {"duty_cycle_sp": 101} in payloads
    assert {"duty_cycle_sp": "20"} in payloads


def test_postman_collection_contains_ev3dev2_gateway_unavailable_503_regression():
    collection = json.loads(COLLECTION_PATH.read_text())
    variables = {item.get("key"): item.get("value") for item in collection.get("variable", [])}
    assert variables.get("runEv3dev2GatewayUnavailableTests") == "false"

    folder = next(
        item
        for item in collection["item"]
        if item.get("name") == "10 - EV3Dev2 Gateway Unavailable - Conditional 503 Regression"
    )

    routes = {
        (item["request"]["method"], item["request"]["url"]["raw"])
        for item in folder["item"]
    }
    required = {
        ("GET", "{{baseUrl}}/api/ev3dev2/motor/catalog"),
        ("GET", "{{baseUrl}}/api/ev3dev2/motor/objects"),
        ("GET", "{{baseUrl}}/api/ev3dev2/motor/operations"),
        ("GET", "{{baseUrl}}/api/ev3dev2/motor/members/OUTPUT_A"),
        (
            "GET",
            "{{baseUrl}}/api/ev3dev2/motor/objects/__gateway_unavailable_probe__/properties/position",
        ),
        (
            "POST",
            "{{baseUrl}}/api/ev3dev2/motor/objects/__gateway_unavailable_probe__/properties/ramp_up_sp",
        ),
        (
            "POST",
            "{{baseUrl}}/api/ev3dev2/motor/objects/__gateway_unavailable_probe__/methods/off",
        ),
        (
            "DELETE",
            "{{baseUrl}}/api/ev3dev2/motor/objects/__gateway_unavailable_probe__",
        ),
        ("POST", "{{baseUrl}}/api/ev3dev2/motor/objects"),
    }
    assert required.issubset(routes)

    for item in folder["item"]:
        scripts = [
            line
            for event in item.get("event", [])
            if event.get("listen") == "test"
            for line in event.get("script", {}).get("exec", [])
        ]
        source = "\n".join(scripts)
        assert "pm.response.to.have.status(503)" in source
        assert "body.success).to.eql(false)" in source
        assert "body.status_code).to.eql(503)" in source
        assert "ev3dev2.motor gateway is unavailable." in source
