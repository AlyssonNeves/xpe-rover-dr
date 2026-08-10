#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the explicit motor-state publishing boundary."""

from adapters.out_motor_state_publisher import MotorStateStorePublisherAdapter
from ports.motor_state_publisher_port import MotorStatePublisherPort
from infrastructure.state.motor_state_store import MotorStateStore


def test_adapter_implements_motor_state_publisher_port():
    store = MotorStateStore()
    adapter = MotorStateStorePublisherAdapter(store)

    assert isinstance(adapter, MotorStatePublisherPort)


def test_publisher_merges_manual_snapshot_without_exposing_store_to_service():
    store = MotorStateStore()
    store.update_motor("LLM", {
        "code": "LLM",
        "name": "Left Large Motor",
        "position": 321,
        "command_queue_size": 0
    })
    adapter = MotorStateStorePublisherAdapter(store)

    adapter.publish_motor_state("LLM", {
        "speed": 500,
        "connected": True,
        "source": "local-manual-direct"
    })

    state = store.get_motor("LLM")
    assert state["name"] == "Left Large Motor"
    assert state["position"] == 321
    assert state["speed"] == 500
    assert state["connected"] is True
    assert state["source"] == "local-manual-direct"


def test_publisher_copies_input_before_storing_it():
    store = MotorStateStore()
    adapter = MotorStateStorePublisherAdapter(store)
    state = {"state": ["running"]}

    adapter.publish_motor_state("RLM", state)
    state["state"].append("mutated")

    assert store.get_motor("RLM")["state"] == ["running"]
