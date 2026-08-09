# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This initial version establishes the project repository, development environment and base source-code organization. Functional monitoring and control capabilities will be introduced incrementally in subsequent versions.

## Platform

- LEGO MINDSTORMS EV3
- ev3dev
- Python 3
- python-ev3dev2

## Project structure

```text
xpe-rover-dr/
├── adapters/
├── app/
├── assets/
│   └── images/
├── ports/
├── services/
├── .vscode/
├── main.py
├── requirements.txt
├── LICENSE
└── README.md
```

The source tree is organized from the beginning to support separation between application logic, ports, adapters and infrastructure services as the project evolves.

## Installation

Clone the repository:

```bash
git clone https://github.com/AlyssonNeves/xpe-rover-dr.git
```

Access the project directory:

```bash
cd xpe-rover-dr
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Execution

Run the initial application entry point:

```bash
python3 main.py
```

Expected output:

```text
Rover-DR
Initial project structure initialized.
```

## Development environment

The repository includes basic VS Code configuration and recommendations for Python development and EV3/ev3dev integration.

## Architecture

The initial directory structure prepares the project for a modular architecture inspired by Hexagonal Architecture principles. Concrete ports, adapters, monitoring services and application services are intentionally deferred to later increments.

![Hexagonal Architecture](assets/images/hexagonal_architecture.png)

## Status

Initial project structure.

## Author

Developed by DUDA Robotics.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
