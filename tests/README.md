# Automated tests

This directory contains the automated verification assets for the Rover DR
application, including Python unit and regression tests and the Postman REST
API collection.

The Python suite uses `pytest` and `unittest`. Most tests run without EV3
hardware. Hardware-dependent tests are skipped when the optional
`ev3dev2.motor` package is unavailable.

## Scope covered

- Application services and command dispatch
  - `app.command_service.CommandService` target routing and validation;
  - dedicated sensor, motor, controller, state, system, drive and EV3Dev2
    gateway commands;
  - invalid parameters, unavailable ports and edge cases.

- Rover application assembly and lifecycle
  - component wiring and monitor criticality;
  - start, restart and idempotent shutdown behavior;
  - monitor shutdown preparation before stop;
  - managed-resource cleanup and failure logging.

- Monitor infrastructure and state stores
  - `MonitorBase` lifecycle and failure diagnostics;
  - sensor, motor and controller state publication;
  - copy isolation, clear operations and not-found behavior;
  - motor queue, worker, cancellation and cleanup behavior.

- Motor control and safety
  - timed, continuous, direct and position commands;
  - synchronized execution, priority and movement profiles;
  - watchdog, timeout, stalled detection and stop actions;
  - differential-drive operations and `DriveService` navigation;
  - guarded EV3Dev2 operations, reservations and lifecycle cleanup.

- EV3Dev2 motor-domain gateway
  - supported class and method allowlists;
  - motor address validation and Rover motor binding;
  - operation classification and required safety parameters;
  - authentication, object lifecycle, safe deletion and standardized
    unavailable-gateway responses.

- REST API and Postman regression
  - route dispatch and response contracts;
  - JSON and `Content-Length` validation;
  - CORS and `OPTIONS` handling;
  - shutdown and restart authentication;
  - dedicated motor-domain routes and generic EV3Dev2 gateway routes;
  - conditional hardware-unavailable regression scenarios.

- Ports, adapters, configuration and utilities
  - segregated sensor query/command and motor-state publication contracts;
  - explicit immutable configuration loading without import-time I/O;
  - single composition-root and dependency-direction regression tests;
  - logging format and timestamps;
  - `CommandResult` serialization and Rover state consolidation.

## How to run

From the project root, run the complete quality pipeline:

```bash
./scripts/quality.sh
```

For a direct functional test run without coverage instrumentation:

```bash
pytest -q
```

To run only the unit tests:

```bash
pytest -q tests/unit
```

## EV3Dev2 gateway unavailable Postman regression

The Postman collection contains the conditional folder
`10 - EV3Dev2 Gateway Unavailable - Conditional 503 Regression`.

To execute it:

1. Start the Rover in an environment where the EV3Dev2 motor gateway is unavailable.
2. Set the collection variable `runEv3dev2GatewayUnavailableTests` to `true`.
3. Run folder `10 - EV3Dev2 Gateway Unavailable - Conditional 503 Regression`.
4. Confirm every request returns HTTP `503` with `success=false`,
   `status_code=503`, and error
   `ev3dev2.motor gateway is unavailable.`

The variable defaults to `false`, preventing this environment-specific group
from failing normal hardware-enabled collection runs.
