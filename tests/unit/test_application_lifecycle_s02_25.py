#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Regression tests for S02.25 centralized application lifecycle."""

import inspect

from adapters.in_rest_api_server import RestApiServer
from app.monitor_registration import MonitorRegistration
from app.rover_application import RoverApplication
from infrastructure.runtime.rover_runtime_context import RoverRuntimeContext
from infrastructure.runtime.threading_application_concurrency import (
    ThreadingApplicationConcurrency
)
from ports.application_concurrency_port import ApplicationConcurrencyPort
from ports.application_server_port import ApplicationServerPort
from ports.process_control_port import ProcessControlPort
from ports.runtime_component_port import RuntimeComponentPort


class FakeProcessControl(ProcessControlPort):
    def __init__(self):
        self.restart_calls = 0

    def restart_current_process(self):
        self.restart_calls += 1


class FakeServer(ApplicationServerPort):
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class FakeRuntimeComponent(RuntimeComponentPort):
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def start(self):
        self.events.append("start:" + self.name)

    def stop(self):
        self.events.append("stop:" + self.name)


class FakeMonitor(object):
    def __init__(self):
        self.critical = None
        self.handler = None

    def set_failure_policy(self, critical=False, failure_handler=None):
        self.critical = bool(critical)
        self.handler = failure_handler

    def get_monitor_name(self):
        return "Fake"


def test_concurrency_implementation_exposes_application_port():
    assert isinstance(ThreadingApplicationConcurrency(), ApplicationConcurrencyPort)


def test_rest_server_exposes_application_server_port():
    assert issubclass(RestApiServer, ApplicationServerPort)


def test_lifecycle_request_has_single_owner():
    concurrency = ThreadingApplicationConcurrency()
    assert concurrency.claim_shutdown_request() is True
    assert concurrency.claim_shutdown_request() is False
    assert concurrency.claim_restart_request() is False
    assert concurrency.is_restart_requested() is False


def test_restart_request_cannot_be_replaced_by_shutdown():
    concurrency = ThreadingApplicationConcurrency()
    assert concurrency.claim_restart_request() is True
    assert concurrency.claim_shutdown_request() is False
    assert concurrency.is_restart_requested() is True


def test_stop_claim_is_idempotent_and_observable():
    concurrency = ThreadingApplicationConcurrency()
    assert concurrency.is_stop_requested() is False
    assert concurrency.claim_stop() is True
    assert concurrency.claim_stop() is False
    assert concurrency.is_stop_requested() is True


def test_runtime_context_delegates_without_lifecycle_flags():
    class FakeApplication(object):
        def __init__(self):
            self.start_calls = 0
            self.shutdown_calls = 0
            self.stop_calls = 0
        def start(self): self.start_calls += 1
        def request_shutdown(self):
            self.shutdown_calls += 1
            return True
        def stop(self): self.stop_calls += 1

    app = FakeApplication()
    context = RoverRuntimeContext(application=app)
    context.start()
    assert context.request_shutdown() is True
    context.stop_or_join()
    assert (app.start_calls, app.shutdown_calls, app.stop_calls) == (1, 1, 1)
    assert not hasattr(context, "_shutdown_lock")
    assert not hasattr(context, "_shutdown_thread")
    assert not hasattr(context, "_restart_requested")


def test_application_requires_explicit_lifecycle_ports():
    server = FakeServer()
    process = FakeProcessControl()
    try:
        RoverApplication(server, None, process)
        assert False, "missing concurrency port must fail"
    except ValueError as error:
        assert "concurrency_port" in str(error)
    try:
        RoverApplication(server, ThreadingApplicationConcurrency(), None)
        assert False, "missing process control port must fail"
    except ValueError as error:
        assert "process_control_port" in str(error)


def test_runtime_components_stop_in_reverse_order():
    events = []
    first = FakeRuntimeComponent("provider", events)
    second = FakeRuntimeComponent("dependent", events)
    app = RoverApplication(
        rest_api_server=FakeServer(),
        concurrency_port=ThreadingApplicationConcurrency(),
        process_control_port=FakeProcessControl(),
        runtime_components=[first, second]
    )
    app.start()
    app.stop()
    assert events == [
        "start:provider", "start:dependent",
        "stop:dependent", "stop:provider"
    ]


def test_monitor_registration_configures_criticality_on_application():
    monitor = FakeMonitor()
    RoverApplication(
        rest_api_server=FakeServer(),
        concurrency_port=ThreadingApplicationConcurrency(),
        process_control_port=FakeProcessControl(),
        monitor_registrations=[MonitorRegistration(monitor, "Fake", True)]
    )
    assert monitor.critical is True
    assert callable(monitor.handler)


def test_rover_application_does_not_own_threading_primitives():
    source = inspect.getsource(RoverApplication)
    assert "threading.Lock" not in source
    assert "threading.Event" not in source
    assert "threading.Thread" not in source


def test_rest_transport_does_not_spawn_lifecycle_thread():
    source = inspect.getsource(RestApiServer._create_handler_class)
    assert "Remote{}Thread" not in source
    assert "lifecycle_thread" not in source
    assert "callback()" in source
