# Rover-DR REST API Contract

## Overview

This increment strengthens the read-only Rover-DR REST API with explicit
command validation and consistent HTTP error handling. The available
functional endpoints remain unchanged; the main evolution is predictable
behavior for invalid requests and unavailable application ports.

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

Every REST response uses `application/json; charset=utf-8`, disables caching
with `Cache-Control: no-store`, and includes basic CORS headers for GET access.

## HTTP status codes

| Status | Meaning in this increment |
| --- | --- |
| `200 OK` | The query was accepted and completed. |
| `204 No Content` | Successful `OPTIONS` preflight response. |
| `400 Bad Request` | Invalid command target, action, parameters or resource-code syntax. |
| `404 Not Found` | Endpoint or requested monitored resource does not exist. |
| `405 Method Not Allowed` | A method other than `GET`/`OPTIONS` was used. |
| `500 Internal Server Error` | An unexpected REST processing failure occurred. |
| `503 Service Unavailable` | A required application output port is not configured. |

Unexpected exceptions are logged internally while the client receives a
generic `500` message instead of implementation details.

## Command validation

`CommandService` validates the command envelope before dispatching it:

- `target` is mandatory and must be a non-empty string;
- `action` is mandatory and must be a non-empty string;
- `params`, when provided, must be a dictionary/JSON object;
- sensor and motor codes are mandatory for single-resource reads;
- sensor and motor codes are normalized to uppercase;
- resource codes must start with a letter and contain only letters, digits,
  `_` or `-`, with a maximum length of 16 characters.

A syntactically valid but unknown sensor or motor code returns `404`.

## Health and Rover state

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Returns basic REST API availability. |
| GET | `/api/rover/state` | Returns one consolidated Rover state snapshot. |

The consolidated snapshot is assembled through the state-backed application
ports introduced in the previous increment.

## Sensors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/sensors` | Lists known sensors. |
| GET | `/api/sensors/all` | Returns complete sensor snapshots. |
| GET | `/api/sensors/{code}` | Returns one sensor snapshot. |

Known initial sensor codes are `TMP`, `GYR`, `RCS`, `LCS` and `TCH`.
Codes are case-insensitive at the application boundary, so `/api/sensors/tmp`
is normalized to `TMP`.

## Motors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/motors` | Lists known motors. |
| GET | `/api/motors/all` | Returns complete motor snapshots. |
| GET | `/api/motors/{code}` | Returns one motor snapshot. |

Known initial motor codes are `LLM`, `LMM`, `RMM` and `RLM`.
Codes are case-insensitive at the application boundary.

## Controller

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/controller/status` | Returns general controller status. |
| GET | `/api/controller/network` | Returns network information. |
| GET | `/api/controller/battery` | Returns battery information. |
| GET | `/api/controller/system` | Returns basic system information. |

## Unsupported methods

The API remains read-only. `POST`, `PUT`, `PATCH` and `DELETE` return:

```json
{
  "success": false,
  "status_code": 405,
  "error": "Only GET and OPTIONS are supported in this API increment"
}
```

The response also contains:

```text
Allow: GET, OPTIONS
```

## Application lifecycle

`RoverApplication` owns startup and orderly shutdown. `main.py` registers
`SIGINT`/`SIGTERM`, starts the application and delegates shutdown to the
lifecycle coordinator. Shutdown and restart are not exposed as REST commands.

## Scope of this increment

This API still contains no motor execution commands, navigation, sensor-mode
changes, remote lifecycle operations, authentication, tokens or global
hardware configuration. Those capabilities are introduced only in their
respective later commits.


## Runtime configuration

The REST host and port defaults are centralized in `app/rover_config.py`. Sensor and motor registry metadata is loaded from `config/rover_config.json`.
