# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This increment centralizes Rover-DR configuration. Runtime defaults are exposed through a single application configuration module, while sensor and motor registry metadata is loaded from `config/rover_config.json` instead of being duplicated inside monitoring services.

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
- Output ports and adapters for monitored information
- Dedicated thread-safe sensor, motor and controller state repositories
- Read-only HTTP/JSON REST API on TCP port `8080`
- Consolidated Rover state through `GET /api/rover/state`
- Validation of command target, action and parameters
- Validation and normalization of sensor/motor resource codes
- Consistent `400`, `404`, `405`, `500` and `503` API responses
- Explicit rejection of unsupported HTTP methods
- Basic CORS/OPTIONS support for read-only clients
- Centralized REST, monitoring and lifecycle runtime defaults
- JSON-based sensor and motor registry configuration
- Startup validation of required configuration sections
- Centralized application status/error logging
- Coordinated startup and orderly shutdown
- `SIGINT` and `SIGTERM` process handling

> Motor execution commands, authentication and physical hardware control are intentionally deferred to later increments.

## Project structure

```text
xpe-rover-dr/
├── adapters/
│   ├── in_rest_api_server.py
│   ├── out_controller_monitor.py
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
│   └── rest_api_contract.md
├── ports/
│   ├── controller_port.py
│   ├── motor_port.py
│   ├── rover_state_query_port.py
│   └── sensor_port.py
├── services/
│   ├── app_logger.py
│   ├── controller_monitor.py
│   ├── controller_state_store.py
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

The project follows the initial boundaries of a Hexagonal Architecture:

1. `rover_config.py` loads centralized runtime settings and registry metadata;
2. monitoring services collect or produce state updates;
3. dedicated `StateStore` repositories keep the latest thread-safe snapshots;
4. output ports define sensor, motor, controller and Rover-state query contracts;
5. output adapters read current state from those repositories;
6. `RoverStateService` consolidates a point-in-time Rover snapshot;
7. `CommandService` validates and coordinates read-only application queries;
8. `RestApiServer` translates HTTP requests into commands and standardizes HTTP responses;
9. `RoverApplication` owns startup and shutdown of runtime components.

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

Example endpoints:

```text
GET /api/health
GET /api/rover/state
GET /api/sensors
GET /api/sensors/TMP
GET /api/motors
GET /api/motors/LLM
GET /api/controller/status
```

The API is read-only in this increment. Requests with `POST`, `PUT`, `PATCH` or `DELETE` return HTTP `405`.

See [`docs/rest_api_contract.md`](docs/rest_api_contract.md) for the complete API and validation rules available in this increment.

Use `Ctrl+C` to request an orderly application shutdown.

## Status

Centralized configuration with monitoring/state repositories, a validated read-only REST API and explicit application lifecycle management.

## Author

Developed by DUDA Robotics.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
