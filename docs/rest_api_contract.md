# Rover-DR REST API Contract

## Overview

This increment keeps the monitoring API read-only and adds a consolidated
Rover state query. Application startup and shutdown are now coordinated by a
single lifecycle component.

### Base URL

```text
http://<host>:8080
```

The default bind address is `0.0.0.0` and the default TCP port is `8080`.
Centralized configuration is intentionally deferred to a later increment.

## Common response format

Successful requests:

```json
{
  "success": true,
  "status_code": 200,
  "data": {}
}
```

Errors:

```json
{
  "success": false,
  "status_code": 404,
  "error": "Endpoint not found"
}
```

## Health and Rover state

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Returns basic REST API availability. |
| GET | `/api/rover/state` | Returns one consolidated Rover state snapshot. |

The consolidated snapshot is assembled from the current monitor-backed output
ports. Dedicated state repositories are not introduced in this increment.

## Sensors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/sensors` | Lists known sensors. |
| GET | `/api/sensors/all` | Returns complete sensor snapshots. |
| GET | `/api/sensors/{code}` | Returns one sensor snapshot. |

Known initial sensor codes are `TMP`, `GYR`, `RCS`, `LCS` and `TCH`.
An unknown sensor code returns HTTP `404`.

## Motors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/motors` | Lists known motors. |
| GET | `/api/motors/all` | Returns complete motor snapshots. |
| GET | `/api/motors/{code}` | Returns one motor snapshot. |

Known initial motor codes are `LLM`, `LMM`, `RMM` and `RLM`.
An unknown motor code returns HTTP `404`.

## Controller

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/controller/status` | Returns general controller status. |
| GET | `/api/controller/network` | Returns network information. |
| GET | `/api/controller/battery` | Returns battery information. |
| GET | `/api/controller/system` | Returns basic system information. |

## Application lifecycle

`RoverApplication` owns the startup and orderly shutdown sequence. `main.py`
registers `SIGINT`/`SIGTERM`, starts the application and delegates shutdown to
that lifecycle coordinator. This increment does **not** expose shutdown or
restart as HTTP commands.

## Scope of this increment

The API intentionally contains no motor execution commands, navigation,
sensor-mode changes, remote lifecycle operations, authentication, tokens or
global hardware configuration. Dedicated sensor, motor and controller state
repositories are introduced in the next commit.
