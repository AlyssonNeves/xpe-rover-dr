# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This increment introduces the first functional services of the project: periodic monitoring of sensors, motors and the EV3 controller. The implementation establishes explicit output ports and adapters while keeping hardware access and external APIs outside this stage.

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
- Output ports for sensors, motors and controller information
- Output adapters connecting the monitoring services to those ports

> Physical EV3 motor control, REST services, centralized configuration and dedicated state repositories are intentionally deferred to later increments.

## Project structure

```text
xpe-rover-dr/
├── adapters/
│   ├── out_controller_monitor.py
│   ├── out_motor_monitor.py
│   └── out_sensor_monitor.py
├── app/
├── assets/
│   └── images/
├── ports/
│   ├── controller_port.py
│   ├── motor_port.py
│   └── sensor_port.py
├── services/
│   ├── controller_monitor.py
│   ├── monitor_base.py
│   ├── motor_monitor.py
│   └── sensor_monitor.py
├── .vscode/
├── main.py
├── requirements.txt
├── LICENSE
└── README.md
```

## Architecture

The monitoring subsystem follows the initial boundaries of a Hexagonal Architecture:

1. monitoring services maintain the current in-memory state;
2. output ports define the contracts used by the application;
3. output adapters expose each monitor through its corresponding port.

Dedicated state repositories will be introduced later so that monitoring and state persistence can evolve independently.

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

Expected startup output:

```text
Rover-DR
Monitoring services initialized.
Sensors: 5
Motors: 4
Controller: available
Press Ctrl+C to stop.
```

Use `Ctrl+C` for an orderly shutdown of the monitoring threads.

## Status

Sensor, motor and controller monitoring implemented with in-memory state.

## Author

Developed by DUDA Robotics.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
