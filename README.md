# Rover DR by DUDA Robotics

Monitoring and control system for LEGO EV3 running on ev3dev using Python and ev3dev2.

![Rover DR](assets/images/rover_dr.png)

---

## Features

* Sensor monitoring
* Motor monitoring
* REST API integration
* Remote monitoring and control
* Distributed system integration
* EV3 controller management
* Structured logging
* Modular and scalable architecture
* Hexagonal architecture approach

---

## Platform

* LEGO Mindstorms EV3
* ev3dev OS
* Python 3
* ev3dev2

---

## Project Structure

```text
Rover-DR/
├── app/
│   ├── commands/          # Protocol-independent command handlers
│   └── services/          # Application use cases and orchestration
├── ports/                 # Segregated input/output contracts
├── adapters/
│   └── rest/              # Declarative HTTP route table and matching
├── infrastructure/
│   ├── configuration/     # Explicit JSON/environment configuration loader
│   ├── ev3/               # EV3 drivers and guarded motor gateway
│   ├── logging/           # Runtime logging implementation
│   ├── monitoring/        # Sensor, motor and controller coordinators
│   ├── motor/             # Driver repository, scheduler, executors and watchdog
│   ├── runtime/           # Threading, process and runtime-context adapters
│   └── state/             # Thread-safe state stores
├── bootstrap/             # Composition root for each operating graph
├── config/
├── docs/
├── tests/
├── main.py
└── README.md
```

## Architecture

The application follows explicit hexagonal boundaries:

* `app` contains protocol-independent use cases and does not import adapters or infrastructure.
* `ports` contains small, responsibility-specific contracts and does not import implementations.
* `adapters` translate REST, joystick, monitor and hardware interactions.
* `infrastructure` owns EV3 drivers, monitoring threads, registries, logging and state storage.
* `bootstrap` is the only composition root and explicitly defines monitor criticality and lifecycle ownership.

The `LOCAL + MANUAL` graph is deliberately minimal. Joystick input reaches `ManualDriveService` synchronously through `ManualDrivePort`, which delegates only low-level operations to `MotorHardwarePort`. Motor-state publication uses the explicit `MotorStatePublisherPort`; the application service does not depend on a concrete state store. The graph does not construct `MotorMonitor`, command queues, navigation services or the guarded EV3Dev2 gateway. `MECANUM + FIELD` adds only a dedicated physical gyro monitor and a thread-safe latest-heading cache; all EV3 sensor I/O remains outside the joystick thread.

Configuration is loaded explicitly by the composition root into an immutable `RoverConfiguration` snapshot. Importing application modules performs no JSON or environment I/O. `main.py` is only the process entry point and delegates assembly, startup error presentation and operating-mode selection to `bootstrap`.

---

## Installation

Clone the repository into a local directory named `Rover-DR`:

```bash
git clone https://github.com/AlyssonNeves/ROVER_DR.git Rover-DR
```

Access the project directory:

```bash
cd Rover-DR
```

---

## Security Configuration

Rover DR does not provide default operational tokens. Before signal registration, service construction, REST binding, monitor startup, or hardware access, the bootstrap composition root explicitly resolves and validates one immutable configuration snapshot. No configuration file or environment variable is read as an import side effect.

### Configuration resolution and precedence

All business defaults are defined canonically in `app/rover_config.py`. The runtime loader applies a recursive merge in this order:

```text
Python defaults < config/rover_config.json < approved deployment environment overrides
```

The JSON file is an override layer and may contain only the sections that differ from the canonical defaults. Nested mappings are merged deeply, so overriding one Mecanum or joystick property does not discard sibling properties. The default-path JSON file is optional; when it is absent, the Python defaults remain effective. A file explicitly selected through `ROVER_CONFIG_FILE` must exist and be valid. After merging, the complete configuration is validated and frozen before any service or hardware adapter is constructed. Application services do not contain fallback motor codes, speed factors, geometry, joystick calibration, polling intervals, or stop-action values.

The packaged `config/rover_config.json` is intentionally empty (`{}`). Add only deployment-specific differences. An automated regression test rejects packaged JSON leaves that merely repeat their canonical Python default.

Environment access is intentionally limited to deployment concerns. Rover DR recognizes only `ROVER_CONFIG_FILE`, `ROVER_HARDWARE_ENABLED`, `ROVER_SHUTDOWN_TOKEN`, `ROVER_HARDWARE_API_TOKEN`, `ROVER_REST_HOST`, and `ROVER_REST_PORT`. Application version, shutdown policy, motor-gateway limits, motor mappings, polarities, wheel factors, Mecanum parameters, gyro settings, and joystick behavior cannot be changed through environment variables; they remain controlled by the canonical defaults and JSON configuration.

When the configuration is incomplete, the application records the failure through `AppLogger`, displays a concise message on the EV3 LCD when available, emits a repeating audible alert, alternates the EV3 LEDs in red using a police-light pattern, waits for the operator to press any EV3 button, stops the alarm, turns the LEDs off, and exits with status code `1` without an exception traceback.

### Supported environment variables

| Environment variable | Requirement | Purpose |
|---|---|---|
| `ROVER_CONFIG_FILE` | Optional | Selects an external JSON override file; an explicitly selected file must exist. |
| `ROVER_HARDWARE_ENABLED` | Optional | Selects physical EV3 integration or simulation-only execution. |
| `ROVER_REST_HOST` | Optional | Overrides the REST bind address for the deployment environment. |
| `ROVER_REST_PORT` | Optional | Overrides the REST bind port for the deployment environment. |
| `ROVER_SHUTDOWN_TOKEN` | Required | Authorizes remote shutdown and restart requests. |
| `ROVER_HARDWARE_API_TOKEN` | Required when `ROVER_HARDWARE_ENABLED=true` | Authorizes API operations that access or command Rover hardware. |

Use different, randomly generated values for the two tokens. Empty or whitespace-only values are rejected. In hardware mode, startup also fails when both variables contain the same value. Any other `ROVER_*` variable is rejected during startup. This fail-fast rule prevents obsolete variables and typing mistakes from appearing to configure the robot while having no effect.

Never commit real tokens to Git, source code, Postman collections, screenshots, logs, or documentation.

---

## EV3 Deployment

Rover DR separates replaceable application files from persistent, EV3-specific deployment configuration.

### Recommended EV3 directory structure

```text
/home/robot/
├── .rover.env
├── start-rover.sh
└── Rover-DR/
    ├── app/
    ├── adapters/
    ├── bootstrap/
    ├── config/
    ├── infrastructure/
    ├── ports/
    ├── main.py
    └── ...
```

| Path | Responsibility |
|---|---|
| `/home/robot/Rover-DR` | Replaceable application directory downloaded from VS Code or uploaded manually. |
| `/home/robot/.rover.env` | Persistent EV3-specific environment variables and security tokens. |
| `/home/robot/start-rover.sh` | Persistent startup script used by the EV3 screen, VS Code/`brickrun`, and SSH. |

This separation allows `/home/robot/Rover-DR` to be deleted and uploaded again without removing the EV3 security configuration or startup script.

### Configure the EV3 through SSH

Replace `192.168.1.12` if the EV3 uses a different IP address.

#### 1. Connect to the EV3

```bash
ssh robot@192.168.1.12
```

Enter the EV3 password when prompted.

#### 2. Configure the EV3 time zone and automatic clock synchronization

Correct system time is required for reliable application logs, diagnostics, operational timestamps and event correlation.

The LEGO EV3 does not maintain an accurate battery-backed system clock while powered off. Until network synchronization occurs, the system may start with a previously saved date and time. For this reason, automatic network time synchronization should remain enabled.

The EV3 must have Internet access for automatic synchronization. A local SSH or USB connection alone does not necessarily provide Internet connectivity.

##### 2.1. Check the current date, time and time zone

Run:

```bash
timedatectl status
```

Display the current local date and time in a concise format:

```bash
date "+%Y-%m-%d %H:%M:%S %Z %z"
```

Example output for the São Paulo time zone:

```text
2026-07-04 17:30:00 -03 -0300
```

##### 2.2. Configure the time zone

Configure the EV3 to use the São Paulo time zone:

```bash
sudo timedatectl set-timezone America/Sao_Paulo
```

Verify the configuration:

```bash
timedatectl status
```

The output should identify the configured time zone as:

```text
America/Sao_Paulo
```

Use a geographic time-zone identifier instead of manually applying a fixed UTC offset. This allows the operating system to manage the applicable regional time rules.

To list available time zones when deploying the Rover in another region, run:

```bash
timedatectl list-timezones
```

A filtered search can also be used:

```bash
timedatectl list-timezones | grep -i sao
```

##### 2.3. Enable automatic date and time synchronization

Enable network time synchronization:

```bash
sudo timedatectl set-ntp true
```

Verify the system clock configuration:

```bash
timedatectl status
```

Depending on the systemd version installed by ev3dev, the output should report fields similar to:

```text
Time zone: America/Sao_Paulo
Network time on: yes
NTP synchronized: yes
```

Some ev3dev versions may display `NTP enabled` instead of `Network time on`.

Check the time synchronization service directly:

```bash
systemctl status systemd-timesyncd.service --no-pager
```

If the EV3 has Internet access but synchronization is not active, restart the service:

```bash
sudo systemctl restart systemd-timesyncd.service
```

Then verify the status again:

```bash
timedatectl status
date "+%Y-%m-%d %H:%M:%S %Z %z"
```

Automatic synchronization corrects the EV3 clock whenever a suitable network connection becomes available.

##### 2.4. Optional manual date and time configuration

Manual configuration should be used only when the EV3 cannot access a network time server.

Temporarily disable automatic synchronization:

```bash
sudo timedatectl set-ntp false
```

Set the local date and time using the `YYYY-MM-DD HH:MM:SS` format:

```bash
sudo timedatectl set-time "2026-07-04 17:30:00"
```

Verify the result:

```bash
date "+%Y-%m-%d %H:%M:%S %Z %z"
```

Re-enable automatic synchronization when Internet access becomes available:

```bash
sudo timedatectl set-ntp true
```

#### 3. Generate the security tokens

Generate two independent tokens:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Assign one value to `ROVER_SHUTDOWN_TOKEN` and the other to `ROVER_HARDWARE_API_TOKEN`.

If OpenSSL is unavailable, use Python 3:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Each command produces a 256-bit random token. The two values must be different.

#### 4. Create the persistent environment file

Create the file outside the application directory:

```bash
nano /home/robot/.rover.env
```

Add:

```bash
export ROVER_HARDWARE_ENABLED="true"
export ROVER_SHUTDOWN_TOKEN="<generated-shutdown-token>"
export ROVER_HARDWARE_API_TOKEN="<generated-hardware-token>"
```

Replace the placeholders with the generated values.

Save and close nano:

1. Press `Ctrl+O`.
2. Press `Enter` to confirm the filename.
3. Press `Ctrl+X`.

Protect the file so that only the `robot` user can read and modify it:

```bash
chmod 600 /home/robot/.rover.env
```

Because `.rover.env` is outside the repository, it remains available when `/home/robot/Rover-DR` is replaced and is not included in Git commits.

#### 5. Create the persistent startup script

Create:

```bash
nano /home/robot/start-rover.sh
```

Add:

```bash
#!/bin/bash

set -eu

PROJECT_DIR="/home/robot/Rover-DR"
ENV_FILE="/home/robot/.rover.env"
MAIN_FILE="${PROJECT_DIR}/main.py"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Configuration error: ${ENV_FILE} not found."
    exit 1
fi

if [ ! -f "${MAIN_FILE}" ]; then
    echo "Application error: ${MAIN_FILE} not found."
    exit 1
fi

cd "${PROJECT_DIR}"

. "${ENV_FILE}"

exec /usr/bin/python3 "${MAIN_FILE}"
```

Save and close nano:

1. Press `Ctrl+O`.
2. Press `Enter` to confirm the filename.
3. Press `Ctrl+X`.

Make the script executable:

```bash
chmod +x /home/robot/start-rover.sh
```

#### 6. Verify the persistent configuration

Verify the variables without displaying their secret values:

```bash
bash -c '
. /home/robot/.rover.env

test -n "$ROVER_SHUTDOWN_TOKEN" \
    && echo "ROVER_SHUTDOWN_TOKEN: configured" \
    || echo "ROVER_SHUTDOWN_TOKEN: missing"

test -n "$ROVER_HARDWARE_API_TOKEN" \
    && echo "ROVER_HARDWARE_API_TOKEN: configured" \
    || echo "ROVER_HARDWARE_API_TOKEN: missing"

test "${ROVER_HARDWARE_ENABLED:-}" = "true" \
    && echo "ROVER_HARDWARE_ENABLED: true" \
    || echo "ROVER_HARDWARE_ENABLED: not enabled"
'
```

Expected output:

```text
ROVER_SHUTDOWN_TOKEN: configured
ROVER_HARDWARE_API_TOKEN: configured
ROVER_HARDWARE_ENABLED: true
```

---

## VS Code EV3Dev Browser Configuration

The VS Code workspace is always downloaded to `/home/robot/Rover-DR`. After the download, the extension starts the persistent `/home/robot/start-rover.sh` script instead of executing `main.py` directly.

### `.vscode/settings.json`

Add the following property to the existing workspace settings:

```jsonc
{
    // Always downloads the current VS Code project to:
    // /home/robot/Rover-DR
    "ev3devBrowser.download.directory": "Rover-DR"
}
```

The property may coexist with the other editor, Python, terminal, deployment-exclusion, and folder-comparison settings already defined by the project.

### `.vscode/launch.json`

Use the persistent startup script as the remote program:

```jsonc
{
    // VS Code launch configurations for Rover DR.
    "version": "0.2.0",

    "configurations": [
        {
            // Downloads the Rover DR project to the EV3 and then
            // starts it through the persistent deployment script.
            "name": "EV3 - Download and Run Rover DR",

            // Launch configuration provided by the EV3Dev Browser extension.
            "type": "ev3devBrowser",

            // Starts a new execution on the target device.
            "request": "launch",

            // Persistent EV3 startup script. It loads
            // /home/robot/.rover.env and executes
            // /home/robot/Rover-DR/main.py.
            "program": "/home/robot/start-rover.sh"
        }
    ]
}
```

When F5 is pressed, the execution flow is:

```text
VS Code / EV3Dev Browser
        |
        | 1. Downloads the workspace
        v
/home/robot/Rover-DR
        |
        | 2. Executes the configured remote program through brickrun
        v
/home/robot/start-rover.sh
        |
        | 3. Loads the persistent environment
        v
/home/robot/.rover.env
        |
        | 4. Starts the application
        v
/home/robot/Rover-DR/main.py
```

---

## Execution Options

All normal EV3 execution methods use `/home/robot/start-rover.sh`. This ensures that the persistent environment configuration is loaded before `main.py` starts.

### Option 1 — Run from the EV3 screen

From the EV3 file browser:

1. Navigate to `/home/robot`.
2. Select `start-rover.sh`.
3. Press the EV3 center button to execute it.

Do not select `/home/robot/Rover-DR/main.py` directly for normal operation. A process started directly from the EV3 screen may not receive the variables stored in `/home/robot/.rover.env`.

### Option 2 — Run from VS Code

With `.vscode/settings.json` and `.vscode/launch.json` configured as described above:

1. Connect VS Code to the EV3 through the EV3Dev Browser extension.
2. Select **EV3 - Download and Run Rover DR**.
3. Press `F5`.

The extension downloads the project to `/home/robot/Rover-DR` and executes:

```bash
brickrun --directory="/home/robot" "/home/robot/start-rover.sh"
```

The equivalent command may also be executed manually from an EV3 SSH terminal.

### Option 3 — Run directly through SSH

For execution without the VS Code launch action:

```bash
/home/robot/start-rover.sh
```

This uses the same persistent configuration and startup validation as the EV3-screen and VS Code methods.

### Direct `main.py` execution for diagnostics only

Direct execution remains available when the environment file is explicitly loaded in the current shell:

```bash
cd /home/robot/Rover-DR
. /home/robot/.rover.env
python3 main.py
```

Running only the following command is not the recommended EV3 deployment procedure:

```bash
python3 main.py
```

The required environment variables may be unavailable to that process.

### EV3 execution notes

This project uses a local Windows virtual environment only for VS Code IntelliSense and dependency recognition.

When using the EV3 SSH terminal opened by the EV3 Device Browser, the project must run with the native Python environment provided by ev3dev.

VS Code may attempt to activate the local Windows virtual environment inside the EV3 SSH terminal. If a PowerShell-related error such as the following is displayed, it can be safely ignored:

```text
-bash: syntax error near unexpected token '&'
```

---

## Updating the Application on the EV3

Stop Rover DR before replacing the application.

Remove only the replaceable application directory:

```bash
rm -rf /home/robot/Rover-DR
```

Upload or download the new version to:

```text
/home/robot/Rover-DR
```

Confirm that the application entry point exists:

```bash
test -f /home/robot/Rover-DR/main.py \
    && echo "Rover DR application found" \
    || echo "Rover DR application missing"
```

The following persistent files must not be removed during a normal application update:

```text
/home/robot/.rover.env
/home/robot/start-rover.sh
```

After the new version is available, start Rover DR from the EV3 screen, through VS Code, or through SSH.

### Stopping a running application

Use the normal EV3 stop action or the VS Code stop action whenever available.

If the application continues running, connect through SSH and request a normal termination:

```bash
pkill -TERM -f "/home/robot/Rover-DR/main.py"
```

If the process does not terminate, force it to stop:

```bash
pkill -KILL -f "/home/robot/Rover-DR/main.py"
```

---

## Temporary and Diagnostic Security Configuration

### Temporary configuration for the current SSH session

For a temporary test without loading `/home/robot/.rover.env`, run:

```bash
export ROVER_HARDWARE_ENABLED=true
export ROVER_SHUTDOWN_TOKEN="<generated-shutdown-token>"
export ROVER_HARDWARE_API_TOKEN="<generated-hardware-token>"
```

Then start the application from the project directory. These values are lost when the SSH session ends or the EV3 restarts.

### Simulate missing security tokens

Use this diagnostic procedure to validate the controlled startup-error screen, audible alert, LED pattern, log message, button acknowledgement, and exit behavior without deleting or modifying `/home/robot/.rover.env`.

Do not use `/home/robot/start-rover.sh` for this test, because the startup script intentionally loads the real persistent tokens. Instead, execute `main.py` directly in a child process whose environment has the token variables removed.

#### Simulate both tokens missing through `brickrun`

This option most closely reproduces execution initiated by VS Code or the EV3 launcher:

```bash
env \
    -u ROVER_SHUTDOWN_TOKEN \
    -u ROVER_HARDWARE_API_TOKEN \
    ROVER_HARDWARE_ENABLED=true \
    brickrun --directory="/home/robot/Rover-DR" \
    "/home/robot/Rover-DR/main.py"
```

Setting `ROVER_HARDWARE_ENABLED=true` ensures that both security variables are required during the diagnostic test, regardless of the value stored in `config/rover_config.json`.

The expected log output includes a controlled configuration error similar to:

```text
Configuration error: Missing required security configuration: ROVER_SHUTDOWN_TOKEN, ROVER_HARDWARE_API_TOKEN. Define the environment variable(s) before starting Rover DR.
```

The EV3 should present the startup-error screen and wait for the operator to press any EV3 button before terminating the program.

#### Simulate both tokens missing through Python

The same validation can be run without `brickrun`:

```bash
cd /home/robot/Rover-DR

env \
    -u ROVER_SHUTDOWN_TOKEN \
    -u ROVER_HARDWARE_API_TOKEN \
    ROVER_HARDWARE_ENABLED=true \
    /usr/bin/python3 main.py
```

#### Simulate one missing token

Test only the shutdown token:

```bash
cd /home/robot/Rover-DR

env \
    -u ROVER_SHUTDOWN_TOKEN \
    ROVER_HARDWARE_ENABLED=true \
    /usr/bin/python3 main.py
```

Test only the hardware API token:

```bash
cd /home/robot/Rover-DR

env \
    -u ROVER_HARDWARE_API_TOKEN \
    ROVER_HARDWARE_ENABLED=true \
    /usr/bin/python3 main.py
```

These commands modify only the environment inherited by the diagnostic child process. They do not change the current SSH session, `/home/robot/.rover.env`, the application configuration, or any stored token value.

After completing the test, start Rover DR normally through the persistent startup script:

```bash
/home/robot/start-rover.sh
```

Or reproduce the normal VS Code execution path:

```bash
brickrun --directory="/home/robot" "/home/robot/start-rover.sh"
```

A shutdown request may send the configured shutdown token in the `X-Rover-Token` header, as a Bearer token, or in the request body according to the REST contract. Motor-domain requests use the dedicated `X-Rover-Hardware-Token` header or the supported authorization mechanism documented in `docs/MOTOR_GATEWAY_SECURITY_AND_LIFECYCLE.md`.

---

## Distributed Architecture Ready

Although Rover DR runs locally on the LEGO EV3, its architecture was designed to support distributed solutions through the REST API layer.

The implemented REST endpoints allow external systems to:

* Monitor rover status in real time
* Retrieve sensor information remotely
* Query motor and controller states
* Execute control commands
* Perform operational diagnostics
* Integrate with supervisory systems

This enables the development of higher-level applications such as:

* Web dashboards
* Remote control panels
* Mobile applications
* Fleet management systems
* IoT monitoring platforms
* Educational robotics control centers

### Example Distributed Architecture

```text
+---------------------+
| Web Dashboard       |
| Mobile Application  |
| Monitoring System   |
+----------+----------+
           |
           | HTTP / REST
           |
+----------v----------+
| Rover DR REST API   |
| Running on EV3      |
+----------+----------+
           |
           |
+----------v----------+
| Sensors / Motors    |
| EV3 Controller      |
+---------------------+
```

The Hexagonal Architecture approach adopted by Rover DR simplifies the integration of new interfaces and external systems without impacting the core application logic.

---

## Architecture

The project follows a modular architecture inspired by Hexagonal Architecture principles, separating:

* Application layer
* Ports
* Adapters
* Infrastructure services

This structure improves maintainability, scalability, and testability.

The REST API layer acts as a gateway between the rover and external systems, enabling the construction of distributed monitoring and control solutions such as web applications, mobile applications, IoT platforms, and educational robotics environments.

![Hexagonal Architecture](assets/images/hexagonal_architecture.png)

---

## Status

Project under active development.

The authoritative application version is defined by `app.rover_config.APPLICATION_VERSION`.

Current version provides:

* Modular rover application lifecycle
* Sensor, motor, and controller monitoring
* REST-based monitoring and control services
* Structured diagnostics and health monitoring
* Foundation for distributed robotic systems
* Mecanum front/rear drivetrain RPM compensation

---

## Author

Developed by DUDA Robotics.

---

## Future Evolution

The current architecture was intentionally designed to support future expansion beyond a standalone EV3 application.

Potential evolutions include:

* Browser-based monitoring dashboards
* Remote rover operation over local networks or the Internet
* Mobile control applications
* Multi-rover fleet management
* Cloud-based telemetry collection
* IoT platform integration
* Artificial Intelligence and autonomous navigation modules
* Real-time operational analytics

The existing REST API and Hexagonal Architecture provide the foundation required to implement these capabilities while preserving the separation between business logic, hardware interfaces, and external systems.

## Motor hardware default and safety

Rover hardware access is enabled by the canonical Python default `hardware_enabled: true`; `config/rover_config.json` may override it, and `ROVER_HARDWARE_ENABLED` has the final deployment precedence. This is the intended EV3 deployment behavior. Development environments without EV3Dev2 remain operational and expose the backend as unavailable; they should explicitly override the setting when simulation-only behavior is required.

The motor subsystem supports regulated continuous, timed, relative-position and absolute-position commands, plus native direct duty-cycle control (`run-direct`). Direct mode accepts values from -100 to 100 and is protected by a watchdog.

The Postman collection includes an advanced motor and navigation folder. Because those requests can move physical hardware, secure the Rover on a test stand, keep wheels clear, and run the stop requests immediately after each motion sequence.

## Safety-managed `ev3dev2.motor` domain

The application provides controlled coverage of the supported EV3Dev2 motor domain through `/api/ev3dev2/motor`. The gateway is intentionally restricted to the approved motor and movement classes, methods, properties, constants and exceptions documented in `docs/ev3dev2_motor_complete_api.md` and the traceability manifest `docs/ev3dev2_motor_api_manifest.json`. Unsupported or unsafe reflective access is rejected by design.

Authenticated operational observability is available through `GET /api/ev3dev2/motor/operations`, which reports gateway-managed operations without expanding the allowed motor API surface.

### EV3Dev2 motor gateway security

The safety-managed EV3Dev2 motor endpoints require a dedicated
`ROVER_HARDWARE_API_TOKEN`. Continuous calls must include `rover_watchdog_ms`, and
non-blocking or `wait*` calls must include `rover_timeout_ms`. See
`docs/MOTOR_GATEWAY_SECURITY_AND_LIFECYCLE.md` and
`docs/MOTOR_PHYSICAL_QUALIFICATION_PROTOCOL.md`.

---

## Quality gates

Run the complete local quality pipeline with:

```bash
./scripts/quality.sh
```

The pipeline compiles production modules, validates Python 3.5 syntax compatibility, runs Flake8 with a cyclomatic-complexity limit of 15, executes real HTTP integration tests separately from instrumented tests, enforces combined line/branch coverage of at least 70%, and applies individual coverage floors to safety-critical modules.

Version v0.68.0 removes duplicated REST defaults from the HTTP adapter, requires explicit transport and security configuration, and adds architectural protection against adapter-owned business defaults. See `docs/RELEASE_NOTES_v0.68.0.md`; the most recent instrumented coverage baseline is documented in `tests/COVERAGE_SUMMARY.md`.

---

## Rover operation modes and local manual joystick control

The application owns the complete selected mode in one application-layer structure: `RoverOperationMode`, managed by `OperationModeService`. This is the single source of truth shared with the composition root, status display, state query service, command authorization and joystick service. EV3 adapters only collect operator choices through ports; they do not own runtime state.

The structure always contains the same five keys:

```json
{
  "command": "LOCAL",
  "control": "MANUAL",
  "front": "NOSE",
  "drive": "DIFFERENTIAL",
  "centric": null
}
```

Applicability is enforced by the value object rather than repeated by consumers:

- `Command = REMOTE` makes `control`, `front`, `drive` and `centric` not applicable (`null`).
- `Command = LOCAL` requires `Control`, `Front` and `Drive`.
- `Drive = DIFFERENTIAL` makes `Centric` not applicable (`null`).
- `Drive = MECANUM` requires `Centric = CHASSIS` or `FIELD`.

At startup, the EV3 first displays **Screen 02 - Command Control**. When `REMOTE` is selected, the Control row is disabled and startup skips all local-drive choices. When `LOCAL` is selected, the EV3 displays **Screen 04 - Front Drive Centric** for both `MANUAL` and `AUTOMATIC` control. The Centric row is disabled for `DIFFERENTIAL` and enabled for `MECANUM`. `MECANUM + FIELD` is accepted only with EV3 hardware enabled and a configured gyro heading source.

The editable SVG masters remain under `assets/screens`, while every deployable EV3 display asset is a ready-to-use 1-bit PBM file under `assets/screens/cache`. Every processed EV3 brick-button press emits a short best-effort confirmation beep; Left, Right and Enter alternate values on active rows, while Enter confirms on the confirmation row. The general status screen emits three short operator-attention beeps when it first appears.

When EV3 hardware is enabled, startup validates and preloads every PBM directly from `assets/screens/cache`. Runtime TIFF conversion, source hashing, manifest maintenance and PBM generation are no longer performed. A missing, corrupted, non-monochrome or incorrectly sized PBM is reported and retried when the affected screen is displayed. During a local-manual Bluetooth failure, **Screen 03 - Bluetooth Error** is shown with the retry interval; the general status screen is restored immediately after reconnection.

Joystick control is enabled only for `LOCAL + MANUAL`. This mode uses a dedicated synchronous path: `JoystickControlService` depends on `ManualDrivePort`, implemented by `ManualDriveService`; the service delegates low-level hardware primitives to `Ev3MotorHardwareAdapter` through `MotorHardwarePort` and publishes read-only telemetry through `MotorStatePublisherPort`. The general `SensorMonitor`, `MotorMonitor`, `ControllerMonitor`, command queues, navigation service, motor watchdogs and EV3Dev2 write gateway are not constructed in this graph. In `MECANUM + FIELD`, only `GyroHeadingMonitor` is added as a critical monitor.

`Front = TAIL` inverts traction polarity and exchanges the logical left/right outputs so that steering remains consistent with the operator-selected front. Physical motor polarity remains an independent hardware-configuration concern.

Default mapping for a controller reported by Linux as `Wireless Controller`:

| Control | `DIFFERENTIAL` | `MECANUM + CHASSIS` | `MECANUM + FIELD` |
|---|---|---|---|
| R2 | Not used | Not used | Not used |
| L2 | Not used | Not used | Not used |
| Left stick X | Not used | Chassis-relative right/left translation | Field-relative right/left translation |
| Left stick Y | Forward/backward translation | Chassis-relative forward/backward translation | Field-relative forward/backward translation |
| Right stick X | Clockwise/counterclockwise rotation (`ABS_RX`) | Clockwise/counterclockwise rotation (`ABS_RX`) | Rover rotation; translation remains field-relative |
| D-pad up/down | Left medium motor (`LMM`) | Disabled because the medium motors are traction motors | Disabled because the medium motors are traction motors |
| D-pad left/right | Right medium motor (`RMM`) | Disabled because the medium motors are traction motors | Disabled because the medium motors are traction motors |
| X button | Immediately stops all manual motors | Immediately stops all four traction motors | Immediately stops all four traction motors |
| Triangle button | No action | No action | Sets the current fresh gyro heading as FIELD zero when all traction axes are neutral |

Analog-stick displacement directly controls motor speed in both drive systems. Each active axis uses the configured center/dead zone followed by the existing signed exponential response, giving low sensitivity near the center and full speed at the limit. R2 and L2 no longer gate or modify traction.

Differential control uses normalized arcade-drive mixing:

```text
translation = -left-stick Y
rotation    = right-stick X
left        = translation + rotation
right       = translation - rotation
denominator = max(abs(left), abs(right), 1)
left        = left / denominator
right       = right / denominator
```

This supports proportional curves and rotation in place while ensuring neither logical motor output exceeds the configured `max_speed_sp`.

For Chassis-centric Mecanum control, the shaped joystick values are `x = left-stick X * strafe_compensation`, `y = -left-stick Y`, and `rx = right-stick X`. Linux evdev defines analog-stick up as negative and down as positive, so Y is intentionally negated to make forward positive. The default `strafe_compensation` is `1.1`. The logical wheel ratios are:

```text
denominator = max(abs(y) + abs(x) + abs(rx), 1)
front-left  = (y + x + rx) / denominator
rear-left   = (y - x + rx) / denominator
front-right = (y - x - rx) / denominator
rear-right  = (y + x - rx) / denominator
```

The denominator normalizes all four ratios together and preserves the relative contribution of translation and rotation. `MECANUM + TAIL` changes only the operator-facing front convention; the Mecanum wheel equations remain unchanged.

For FIELD-centric Mecanum control, `GyroHeadingMonitor` reads only the physical gyro in its own monitor thread and writes the latest angle into `HeadingStateStore`. The joystick thread reads a minimal cached tuple through `HeadingQueryPort`; it never reads `/sys`, constructs an EV3 sensor, waits for a monitor cycle or invokes the general sensor monitor. With operational FIELD heading `h` derived from the canonical, mounting-corrected gyro value and the current runtime-zero reference, the field translation vector is converted to the Rover frame before wheel mixing:

```text
rover_x = field_x * cos(h) - field_y * sin(h)
rover_y = field_x * sin(h) + field_y * cos(h)
```

The default gyro poll interval is 20 ms and a sample older than 100 ms is rejected. A missing or stale heading immediately stops traction once and requires all active traction axes to return to neutral before motion can resume. Repeated physical read failures make the dedicated gyro monitor fail critically and trigger the normal controlled application shutdown.

The operational FIELD zero can be redefined while the application is running. With all three traction axes neutral, point the Rover toward the desired FIELD-forward direction and press the configured Triangle button. `FieldHeadingReferenceService` stores the current fresh canonical heading in memory and the joystick then uses `normalize(canonical_heading - runtime_zero)`. The physical sensor is not reset, the canonical cache and REST value are not changed, and the reference is cleared on application restart. Requests made during motion or without a fresh heading are rejected and logged.

The default Mecanum mapping is `LLM` front-left, `LMM` rear-left, `RLM` front-right and `RMM` rear-right. Mode-specific speed factors and global motor polarity remain independently configurable in `config/rover_config.json`.

The FIELD heading configuration is isolated from the general sensor monitor:

```json
"field_heading": {
  "sensor_code": "GYR",
  "poll_seconds": 0.02,
  "max_age_seconds": 0.1,
  "reset_on_start": true,
  "angle_sign": -1.0,
  "angle_offset_deg": 0.0,
  "runtime_recenter_enabled": true,
  "recenter_requires_neutral": true,
  "max_consecutive_failures": 3
}
```

The deployed Rover uses `angle_sign = -1.0` because the gyroscope is mounted upside down. The EV3 gyro adapter applies the sign and static offset before publishing the sample, so the cache and REST sensor value consume the same canonical heading. Use `angle_offset_deg` only for a fixed installation correction; use Triangle for the temporary operator FIELD reference.

The `joystick` section configures the evdev name, Bluetooth address, automatic connection, retry/timeout intervals, maximum speeds, `axis_center`, `axis_deadzone`, `axis_max`, `axis_response_intensity`, auxiliary motor codes and polling interval. Values inside `axis_deadzone` are neutral; the remaining travel is rescaled to the full normalized range before the configured exponential response is applied. A typical automatic-reconnection configuration is:

```json
"joystick": {
  "device_name": "Wireless Controller",
  "device_address": "AA:BB:CC:DD:EE:FF",
  "auto_connect": true,
  "connection_retry_seconds": 3.0,
  "connection_timeout_seconds": 10.0,
  "passive_reconnect_seconds": 4.0,
  "discovery_poll_seconds": 0.25,
  "axis_center": 127,
  "axis_deadzone": 7,
  "axis_max": 255,
  "axis_response_intensity": 2.0,
  "button_codes": {
    "emergency_stop": 304,
    "field_recenter": 307
  }
}
```

The controller must be paired and trusted once in BlueZ. When `LOCAL + MANUAL` starts, the adapter first checks whether the configured evdev device already exists. If it does not, it waits up to `passive_reconnect_seconds` for the paired controller to reconnect naturally and create its evdev nodes. Only after that passive phase expires does it send `connect <device_address>` through the legacy interactive `bluetoothctl` session. Both phases share the single `connection_timeout_seconds` budget, and the complete cycle is retried after `connection_retry_seconds` when it fails. The same sequence is used after an in-operation disconnect.

During every disconnected interval, Rover synchronously stops all manual motors, releases the manual-control session and discards all previous axis values. After startup or reconnection, traction remains blocked until every active analog axis has been observed at neutral. REST motor and navigation writes return `409` while read-only state queries remain available through thread-free query adapters.

### Discover, pair and trust the Wireless Controller

Prepare the controller once on the EV3 before enabling automatic reconnection. Stop Rover DR while performing the procedure; otherwise the running application may issue its own connection attempts.

#### 1. Open the Bluetooth control shell

From the EV3 SSH terminal, run:

```bash
bluetoothctl
```

The prompt changes to `[bluetooth]#`. The following commands are entered inside that prompt:

```text
power on
agent on
default-agent
```

#### 2. Obtain the controller Bluetooth address

First list devices already known by BlueZ:

```text
devices
```

A detected controller is normally displayed as:

```text
Device 41:42:76:52:94:E8 Wireless Controller
```

The six hexadecimal pairs are the Bluetooth address, also called the MAC address. In the example, the address is `41:42:76:52:94:E8`. Use the address reported by the EV3, not the example address.

The same list can be requested directly from the normal SSH shell without entering the interactive prompt:

```bash
bluetoothctl devices
```

If `Wireless Controller` is not listed, make the controller discoverable, start scanning and wait for a line containing its name:

```text
scan on
```

Turn on or wake the controller while scanning. When a line similar to the following appears, copy the address:

```text
[NEW] Device 41:42:76:52:94:E8 Wireless Controller
```

Then stop scanning:

```text
scan off
```

#### 3. Pair the controller

Replace `<controller-address>` with the address obtained above:

```text
pair <controller-address>
```

Wait for a success message. If BlueZ requests confirmation or authorization, accept it on the EV3.

#### 4. Mark the controller as trusted

Trusted devices may reconnect without requiring a new authorization after each restart:

```text
trust <controller-address>
```

#### 5. Connect the controller

Ensure that the controller is powered on and then run:

```text
connect <controller-address>
```

#### 6. Verify pairing, trust and connection

Run:

```text
info <controller-address>
```

The relevant fields should be similar to:

```text
Name: Wireless Controller
Paired: yes
Trusted: yes
Blocked: no
Connected: yes
```

`Connected: no` is acceptable when the controller is intentionally turned off, but `Paired` and `Trusted` should remain `yes`.

Exit `bluetoothctl` with:

```text
quit
```

#### 7. Confirm that Linux created the evdev input device

After connecting the controller, run from the normal SSH shell:

```bash
for file in /sys/class/input/event*/device/name; do
    echo "$file: $(cat "$file")"
done
```

At least one line should end with:

```text
Wireless Controller
```

The value must match the configured `joystick.device_name`.

#### 8. Configure Rover DR with the controller address

Set the discovered address in `config/rover_config.json`:

```json
"joystick": {
  "device_name": "Wireless Controller",
  "device_address": "41:42:76:52:94:E8",
  "auto_connect": true
}
```

Use the address reported by the EV3. Leaving `device_address` empty keeps the safety retry loop active but prevents Rover from issuing an automatic Bluetooth connection command.

#### Useful maintenance commands

Connect an already paired and trusted controller from the SSH shell:

```bash
bluetoothctl connect <controller-address>
```

Disconnect it while preserving pairing and trust:

```bash
bluetoothctl disconnect <controller-address>
```

Stop Rover DR before manually disconnecting the controller; otherwise automatic reconnection will attempt to connect it again.

Display the current status:

```bash
bluetoothctl info <controller-address>
```

Remove the device only when a complete re-pairing is required:

```bash
bluetoothctl remove <controller-address>
```

`remove` deletes the pairing and trust records. It is not required for a normal disconnection.

Install the evdev dependency on the EV3 with:

```bash
pip3 install -r requirements.txt
```

Confirm that Linux detects the controller before starting Rover DR:

```bash
python3 -m evdev.evtest
```
