# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This increment adds the first differential-drive abstraction above the motor command layer. The Rover can now treat the configured left and right traction motors as one drive subsystem, issue independent tank-style setpoints and stop both sides through a single application command while retaining the watchdog and motor-safety mechanisms introduced earlier.

## Platform

- LEGO MINDSTORMS EV3
- ev3dev
- Python 3
- python-ev3dev2

## Current capabilities

- Periodic monitoring infrastructure based on threads
- Sensor registry and state queries
- Motor registry and state queries
- Controller, network, battery and system status queries
- Dedicated thread-safe sensor, motor and controller state repositories
- HTTP/JSON REST API on TCP port `8080`
- Consolidated Rover state through `GET /api/rover/state`
- Centralized runtime and hardware registry configuration
- Physical `LargeMotor` and `MediumMotor` integration through `python-ev3dev2`
- Live EV3 motor position, speed, duty cycle, state, driver name, maximum speed and polarity
- Per-motor asynchronous command queues
- Numeric command priorities from `0` to `100`, where `100` is highest
- Stable FIFO ordering between commands with the same priority
- Public `command_id` lifecycle tracking (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `STALLED`)
- Command history queries globally or per motor
- Cancellation of queued and active motor work
- Immediate stop that preempts pending work for the selected motor
- Synchronized multi-motor batches with shared `batch_id` and scheduled start timestamp
- Queued `run-timed`, `run-forever`, `run-to-rel-pos` and `reset` operations
- Validated speed, duration, position, stop action and priority parameters
- Monotonic execution deadlines for bounded motor movements
- Automatic watchdog for `run-forever` commands
- Driver-level and logical stall detection based on motor progress
- Centralized default safe-stop action (`brake`)
- Native EV3 acceleration/deceleration ramps before movement
- Safety event metadata exposed in motor state snapshots
- Differential-drive service using configured `LLM` and `RLM` traction motors
- Independent left/right tank speed control through a synchronized motor batch
- Unified drive status and two-motor stop operations
- Consistent `400`, `404`, `405`, `500` and `503` API responses
- Basic CORS/OPTIONS support
- Graceful fallback when EV3 motor hardware or `ev3dev2` is unavailable
- Coordinated startup and orderly shutdown
- `SIGINT` and `SIGTERM` process handling


## Project structure

```text
xpe-rover-dr/
├── adapters/
│   ├── in_rest_api_server.py
│   ├── out_controller_monitor.py
│   ├── out_drive_service.py
│   ├── out_motor_monitor.py
│   ├── out_rover_state_query.py
│   └── out_sensor_monitor.py
├── app/
│   ├── command_service.py
│   ├── models.py
│   ├── rover_application.py
│   └── rover_config.py
├── assets/
│   └── images/
├── config/
│   └── rover_config.json
├── docs/
│   ├── motor_hardware_validation.md
│   └── rest_api_contract.md
├── ports/
│   ├── controller_port.py
│   ├── drive_port.py
│   ├── motor_port.py
│   ├── rover_state_query_port.py
│   └── sensor_port.py
├── services/
│   ├── motor/
│   │   ├── __init__.py
│   │   └── registries.py
│   ├── app_logger.py
│   ├── controller_monitor.py
│   ├── controller_state_store.py
│   ├── drive_service.py
│   ├── monitor_base.py
│   ├── motor_monitor.py
│   ├── motor_state_store.py
│   ├── rover_state_service.py
│   ├── sensor_monitor.py
│   └── sensor_state_store.py
├── tests/
│   └── postman/
│       └── rover_dr_rest_api_collection.json
├── .vscode/
├── main.py
├── requirements.txt
├── LICENSE
└── README.md
```

## Architecture

The project continues to follow Hexagonal Architecture boundaries:

1. `rover_config.py` loads centralized runtime settings and hardware definitions;
2. monitoring services collect physical state and own runtime execution workers;
3. `MotorCommandRegistry` stores externally consultable command lifecycle records;
4. one priority queue and one worker are maintained per configured motor;
5. thread-safe `StateStore` repositories keep current hardware snapshots;
6. output ports define query and motor-orchestration contracts;
7. adapters expose the stores, motor service and differential-drive service to the application layer;
8. `DriveService` coordinates differential drive, encoder odometry, gyroscope heading and basic geometric navigation without accessing EV3 motor hardware directly;
9. `CommandService` validates requests before queue admission;
10. `Ev3Dev2MotorGateway` exposes an allowlisted `ev3dev2.motor` surface through the existing motor safety boundary;
11. `RestApiServer` maps HTTP requests to application commands and gateway operations;
12. `RoverApplication` owns startup and orderly shutdown, including gateway cleanup.

![Hexagonal Architecture](assets/images/hexagonal_architecture.png)

## Installation

```bash
git clone https://github.com/AlyssonNeves/xpe-rover-dr.git
cd xpe-rover-dr
pip install -r requirements.txt
```

## Execution

```bash
python3 main.py
```

The REST API will be available at:

```text
http://<EV3-IP>:8080
```

Examples:

```text
GET  /api/health
GET  /api/rover/state
GET  /api/motors
GET  /api/motors/LLM
POST /api/motors/LLM/run-timed
POST /api/motors/LLM/run-forever
POST /api/motors/LLM/run-to-rel-pos
POST /api/motors/LLM/cancel
POST /api/motors/LLM/stop
POST /api/motors/synchronized
GET  /api/drive/status
POST /api/drive/tank
POST /api/drive/move-distance
POST /api/drive/rotate-angle
POST /api/drive/curve-radius
POST /api/drive/reset-odometry
POST /api/drive/stop
GET  /api/motor-commands
GET  /api/motor-commands/1
GET  /api/motors/LLM/commands
GET  /api/ev3dev2/motor/catalog
GET  /api/ev3dev2/motor/objects
POST /api/ev3dev2/motor/objects
GET  /api/ev3dev2/motor/operations
DELETE /api/ev3dev2/motor/objects/{object_id}
```

A queued command normally returns HTTP `202 Accepted` with its `command_id`. The command lifecycle can then be queried independently.

See [`docs/rest_api_contract.md`](docs/rest_api_contract.md) for the complete API contract, [`docs/ev3dev2_motor_complete_api.md`](docs/ev3dev2_motor_complete_api.md) for the expanded motor-domain catalog, [`docs/MOTOR_GATEWAY_SECURITY_AND_LIFECYCLE.md`](docs/MOTOR_GATEWAY_SECURITY_AND_LIFECYCLE.md) for gateway safety/lifecycle rules, and [`docs/MOTOR_PHYSICAL_QUALIFICATION_PROTOCOL.md`](docs/MOTOR_PHYSICAL_QUALIFICATION_PROTOCOL.md) for physical qualification guidance.

Use `Ctrl+C` to request an orderly application shutdown.

## Status

Centralized configuration, live EV3 motor integration, prioritized command orchestration, synchronized scheduling, motor safety supervision, differential-drive odometry, gyroscope heading, basic geometric navigation and a safety-managed `ev3dev2.motor` gateway.

## Author

Developed by DUDA Robotics.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
