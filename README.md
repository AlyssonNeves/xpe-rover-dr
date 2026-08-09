# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This increment exposes the sensor, motor and controller monitoring capabilities through the first read-only REST API. HTTP concerns remain isolated in an input adapter, while application commands coordinate access to the existing output ports.

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
- Application command service for read-only queries
- HTTP/JSON REST API on TCP port `8080`
- Initial REST API contract and Postman collection

> Motor execution commands, centralized configuration, application lifecycle management, authentication and dedicated state repositories are intentionally deferred to later increments.

## Project structure

```text
xpe-rover-dr/
├── adapters/
│   ├── in_rest_api_server.py
│   ├── out_controller_monitor.py
│   ├── out_motor_monitor.py
│   └── out_sensor_monitor.py
├── app/
│   ├── command_service.py
│   └── models.py
├── assets/
│   └── images/
├── docs/
│   └── rest_api_contract.md
├── ports/
│   ├── controller_port.py
│   ├── motor_port.py
│   └── sensor_port.py
├── services/
│   ├── controller_monitor.py
│   ├── monitor_base.py
│   ├── motor_monitor.py
│   └── sensor_monitor.py
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

1. monitoring services maintain the current in-memory state;
2. output ports define sensor, motor and controller query contracts;
3. output adapters expose the monitoring services to the application layer;
4. `CommandService` coordinates application queries;
5. `RestApiServer` is an input adapter that translates HTTP requests into application commands.

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
GET /api/sensors
GET /api/sensors/TMP
GET /api/motors
GET /api/motors/LLM
GET /api/controller/status
```

See [`docs/rest_api_contract.md`](docs/rest_api_contract.md) for the complete API available in this increment.

Use `Ctrl+C` to stop the application.

## Status

Sensor, motor and controller monitoring exposed through an initial read-only REST API.

## Author

Developed by DUDA Robotics.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
