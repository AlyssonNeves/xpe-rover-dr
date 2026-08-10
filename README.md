# Rover-DR

Educational and experimental mobile robotics platform based on LEGO MINDSTORMS EV3, ev3dev and Python.

![Rover-DR](assets/images/rover_dr.png)

## Objective

Rover-DR provides a modular foundation for the progressive development of monitoring, control, navigation and autonomous robotics capabilities on the LEGO EV3 platform.

This release consolidates deployment configuration for EV3 and simulation environments. A single `ROVER_HARDWARE_ENABLED` switch now controls physical integrations, startup includes operator selection of command/operation mode on the EV3, and deployment/security requirements are documented for reproducible execution.

## Platform

- LEGO MINDSTORMS EV3
- ev3dev
- Python 3
- python-ev3dev2

## Current capabilities

- Hexagonal Architecture with explicit application, port, adapter, infrastructure and bootstrap boundaries
- Dedicated `LOCAL + MANUAL` runtime for low-latency joystick control
- Direct synchronous motor control isolated from monitoring command queues
- Linux joystick integration through `evdev`
- Fail-safe stop and neutral-safety barrier after joystick disconnection
- EV3 graphical mode selection and operational status feedback
- Periodic sensor, motor and controller monitoring for the standard runtime
- Thread-safe state repositories and read-only query adapters
- HTTP/JSON REST API on TCP port `8080`
- Consolidated Rover state through `GET /api/rover/state`
- Explicit motor query, command, guarded-operation and gateway ports
- Declarative REST route table with explicit gateway dispatch
- Shared EV3 motor-driver repository used by monitored and manual-control paths
- Motor state collection extracted from the monitor orchestration
- Centralized concrete composition in `bootstrap/rover_assembly.py`
- Architecture and Python 3.5 compatibility quality gates
- Graceful fallback when EV3 hardware integrations are disabled or unavailable

## Project structure

```text
xpe-rover-dr/
├── adapters/                 # inbound/outbound adapters
│   └── rest/                 # HTTP routing and declarative API route table
├── app/
│   ├── commands/             # focused command handlers
│   ├── services/             # application use cases
│   ├── command_service.py
│   ├── rover_application.py
│   └── rover_config.py
├── bootstrap/
│   └── rover_assembly.py     # concrete composition root
├── infrastructure/
│   ├── ev3/                  # EV3 gateways, drivers and UI helpers
│   ├── logging/              # application logging implementation
│   ├── monitoring/           # runtime monitors
│   ├── motor/                # driver repository and state collection
│   └── state/                # thread-safe state stores
├── ports/                    # focused input/output contracts
├── assets/
├── config/
├── docs/
├── scripts/
├── tests/
└── main.py                   # process entry point
```

The former top-level `services/` package no longer exists. Application services live
under `app/services/`, while monitoring, state, logging and EV3-specific concerns live
under `infrastructure/`.

## Architecture

The S02.10 structure reinforces the dependency direction of the hexagonal design:

1. `app/` contains use cases and orchestration and does not import concrete adapters or infrastructure;
2. `ports/` contains focused contracts and does not depend on application or concrete layers;
3. `adapters/` translate external protocols and application-facing queries;
4. `infrastructure/` implements EV3 hardware, monitoring, logging and state persistence details;
5. `bootstrap/rover_assembly.py` is the single concrete composition point introduced in this increment;
6. `main.py` delegates composition to bootstrap and remains focused on process signals and execution;
7. the `LOCAL + MANUAL` graph retains synchronous motor writes and read-only REST queries, without monitoring queues in its control path;
8. the standard runtime preserves the monitored command path;
9. the broad motor contract is retained only as a compatibility aggregate over focused query, command, guarded-operation and gateway contracts;
10. REST command routing uses an explicit declarative route table rather than reflective dispatch over concrete gateways;
11. `MotorMonitor` delegates EV3 driver access to a shared driver repository and snapshot acquisition to a dedicated state collector;
12. automated architecture checks protect these dependency rules and Python 3.5 compatibility.

![Hexagonal Architecture](assets/images/hexagonal_architecture.png)

The broader application lifecycle abstraction and the final consolidation of runtime/security configuration are intentionally deferred to later Sprint 2 increments.

## Deployment modes

Rover-DR supports two deployment profiles controlled by a single switch:

```bash
export ROVER_HARDWARE_ENABLED=true   # EV3 deployment
export ROVER_HARDWARE_ENABLED=false  # development/simulation
```

When the environment variable is omitted, `hardware_enabled` from `config/rover_config.json` is used. In hardware mode the application enables physical motor/sensor access, startup alerts, the `ev3dev2.motor` gateway and the EV3 operating-mode selector. In simulation mode these physical integrations are skipped and the Rover starts in `LOCAL/MANUAL`.

### EV3 deployment

```bash
export ROVER_HARDWARE_ENABLED=true
export ROVER_SHUTDOWN_TOKEN="<generated-shutdown-token>"
export ROVER_HARDWARE_API_TOKEN="<generated-hardware-token>"
python3 main.py
```

The two tokens must be different. At startup, use the EV3 buttons to select `LOCAL/REMOTE` and `MANUAL/AUTOMATIC`, then confirm with the center button.

### Development without EV3 hardware

```bash
export ROVER_HARDWARE_ENABLED=false
export ROVER_SHUTDOWN_TOKEN="<generated-shutdown-token>"
python3 main.py
```

The hardware API token is not required in this profile because the hardware gateway is not started.

## Installation

```bash
git clone https://github.com/AlyssonNeves/xpe-rover-dr.git
cd xpe-rover-dr
pip install -r requirements.txt
```


## Security configuration

Commit 17 introduces mandatory credentials for remote lifecycle operations and
the reflective `ev3dev2.motor` gateway. Rover-DR does not ship operational
default tokens. Configure both variables before running `main.py`:

```bash
export ROVER_SHUTDOWN_TOKEN="<generated-shutdown-token>"
export ROVER_HARDWARE_API_TOKEN="<generated-hardware-token>"
```

Use different cryptographically random values and never commit them to Git.
`.env.example` documents the variable names but intentionally contains only
placeholders. Startup terminates with status `1` when either token is missing,
blank or when both tokens contain the same value.

The following system operations use `ROVER_SHUTDOWN_TOKEN` and require
`{"confirm": true}` by default:

```text
POST /api/system/shutdown
POST /api/system/restart
```

The token may be supplied in `X-Rover-Token`, as `Authorization: Bearer ...`,
or in the JSON `token` field.

Every `/api/ev3dev2/motor/...` request requires the dedicated
`ROVER_HARDWARE_API_TOKEN`, supplied through `X-Rover-Hardware-Token` or
`Authorization: Bearer ...`. Regular monitoring, motor-command and drive routes
retain their existing behavior in this historical increment.

## EV3 startup alerts

Commit 18 adds an operator-facing fallback for fatal startup configuration errors.
When security validation fails, Rover-DR attempts to show a compact message on the
EV3 console, alternates the left/right status LEDs in red and emits an audible tone.
The alert remains active until the operator acknowledges it by pressing a physical
brick button.

This mechanism is intentionally implemented through the `OperatorAlertPort` output
contract and `StartupErrorNotifier` application service. If the process is running
on a development computer where EV3 display, LED, sound or button interfaces are
unavailable, the adapter fails safely and startup still terminates with status `1`.

The global hardware enable/disable switch and interactive operating-mode selection
are not part of this historical increment; they are introduced in Commit 19.

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
POST /api/system/shutdown
POST /api/system/restart
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

## Arquitetura hexagonal

A camada REST foi separada do despacho de comandos. O transporte HTTP permanece em `adapters/in_rest_api_server.py`, o mapeamento de endpoints fica em `adapters/rest/command_routes.py` e o `CommandService` despacha comandos para handlers explícitos em `app/commands/`. Essa separação evita que detalhes HTTP se propaguem para os serviços e portas do Rover. Consulte `docs/hexagonal_architecture.md`.

## Qualidade e testes automatizados

A partir deste marco, o projeto possui uma suíte unitária organizada por domínio e
quality gates executáveis localmente e no GitHub Actions. O pipeline verifica sintaxe,
regras críticas de lint, complexidade ciclomática e cobertura automatizada mínima de 60%.

```bash
pip install -r requirements-dev.txt
bash scripts/quality.sh
```

Os testes não exigem hardware EV3 físico; dependências de hardware são simuladas nas
verificações automatizadas. Consulte `tests/README.md` para o escopo atual.

## Local manual joystick control

The `LOCAL + MANUAL` application mode now includes an application service that
translates generic joystick events into differential traction commands. Left
stick Y controls forward/backward motion, right stick X controls steering and
rotation, the D-pad controls the two auxiliary Medium motors, and the X button
requests an immediate stop.

This first increment deliberately depends only on the existing `DrivePort` and
`MotorPort`. Linux device discovery and `evdev` integration are kept outside
the application logic and are introduced in the next evolution step.

## Graphical EV3 mode-selection screens

The EV3 operating-mode selector now uses ready-made monochrome PBM artwork sized
for the 178 x 128 brick display. Three visual states are packaged for the current
Command/Control combinations: `LOCAL + MANUAL`, `LOCAL + AUTOMATIC` and `REMOTE`.
The existing EV3 button interaction is preserved while the dynamically drawn
selection screen is replaced by deterministic graphical assets.

This increment intentionally performs direct PBM loading from `assets/screens`.
The complete screen catalogue, deployment cache and in-memory PBM reuse are kept
for the later screen/cache consolidation increment.

## Bluetooth disconnect fail-safe

The `LOCAL + MANUAL` input path now treats evdev descriptor errors and read
failures as a lost Bluetooth joystick connection. Rover-DR synchronously stops
all motors owned by the manual path, invalidates the active manual session and
discards the previous traction/steering state before the worker terminates.

At this stage recovery is intentionally explicit rather than automatic. If the
manual joystick service is started again after the controller reappears, motion
remains blocked until both traction axes have been observed at their neutral
position. Automatic `bluetoothctl` connection/reconnection is reserved for the
later Bluetooth reconnection increment.

## EV3 battery monitoring and operational feedback

When physical EV3 hardware is enabled, Rover-DR now starts an informational
status display using the packaged `Screen 05 - General Status.pbm` artwork. The
screen is refreshed periodically with the EV3 battery percentage, current IP
address, joystick connection state and the selected Command/Control values.
Battery lookup explicitly addresses `legoev3-battery` so a Bluetooth controller
power-supply entry cannot be mistaken for the brick battery.

Processed EV3 brick-button presses also emit a short best-effort confirmation
beep, and the general status screen announces `Rover D R Online` without making
audio availability a startup requirement. Bluetooth recovery states, startup
progress screens and the consolidated PBM cache remain reserved for later
increments.

### S02.08 - Fronteiras arquiteturais do controle manual

O caminho `LOCAL + MANUAL` utiliza contratos explícitos para entrada do joystick,
controle síncrono, escrita física e publicação de estado. O serviço de controle
manual não acessa `MotorMonitor`, `MotorStateStore` ou adaptadores concretos;
estados produzidos pelo caminho direto são publicados por `MotorStatePublisherPort`.

### S02.09 - Consolidação do runtime LOCAL + MANUAL

O modo `LOCAL + MANUAL` passa a possuir um grafo de execução dedicado. Nesse
runtime não são instanciados `SensorMonitor`, `MotorMonitor`, `ControllerMonitor`,
`DriveService` nem `Ev3Dev2MotorGateway`; o joystick controla diretamente o
`ManualDriveService`, que escreve de forma síncrona no hardware e publica os
snapshots de motores para consultas REST somente leitura.

Em hardware real, o composition root conecta automaticamente o
`EvdevJoystickAdapter` ao serviço de controle manual. Sensores e informações do
controlador permanecem consultáveis por adaptadores read-only sem threads de
monitoração, e comandos REST de escrita em motores/drive retornam conflito enquanto
o controle `LOCAL + MANUAL` possui o hardware.
