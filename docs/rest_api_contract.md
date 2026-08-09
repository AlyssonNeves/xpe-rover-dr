# Rover-DR REST API Contract

## Overview

This increment extends the validated Rover-DR REST API with immediate execution
of basic physical motor operations. Read endpoints remain unchanged. Motor
commands are accepted through dedicated `POST` routes and are executed directly
through the configured `python-ev3dev2` motor instance.

No command queue, priority, command identifier, synchronized batch or watchdog
exists in this increment; those mechanisms are introduced later.

### Base URL

```text
http://<host>:8080
```

The default bind address is `0.0.0.0` and the default TCP port is `8080`.

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
  "status_code": 400,
  "error": "Parameter speed_sp must be an integer"
}
```

Every response uses `application/json; charset=utf-8`, `Cache-Control: no-store`
and basic CORS headers.

## HTTP status codes

| Status | Meaning |
| --- | --- |
| `200 OK` | Query completed or a motor command was submitted directly to the driver. |
| `204 No Content` | Successful `OPTIONS` preflight. |
| `400 Bad Request` | Invalid JSON, route parameters or motor command parameters. |
| `404 Not Found` | Endpoint or configured resource does not exist. |
| `405 Method Not Allowed` | `PUT`, `PATCH` or `DELETE` was used. |
| `500 Internal Server Error` | Unexpected REST processing failure. |
| `503 Service Unavailable` | Required port or physical motor backend is unavailable. |

## Read endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | REST API availability. |
| GET | `/api/rover/state` | Consolidated Rover snapshot. |
| GET | `/api/sensors` | Lists sensors. |
| GET | `/api/sensors/all` | Complete sensor snapshots. |
| GET | `/api/sensors/{code}` | One sensor snapshot. |
| GET | `/api/motors` | Lists motors. |
| GET | `/api/motors/all` | Complete motor snapshots. |
| GET | `/api/motors/{code}` | One motor snapshot. |
| GET | `/api/controller/status` | General controller status. |
| GET | `/api/controller/network` | Network information. |
| GET | `/api/controller/battery` | Battery information. |
| GET | `/api/controller/system` | System information. |

Known initial motor codes are `LLM`, `LMM`, `RMM` and `RLM`. Resource codes are
normalized to uppercase at the application boundary.

## Basic motor execution

### Stop

```http
POST /api/motors/{code}/stop
Content-Type: application/json
```

Optional body:

```json
{"stop_action": "brake"}
```

### Run timed

```http
POST /api/motors/{code}/run-timed
Content-Type: application/json
```

```json
{
  "speed_sp": 300,
  "time_sp": 1000,
  "stop_action": "brake"
}
```

`time_sp` is expressed in milliseconds.

### Run forever

```http
POST /api/motors/{code}/run-forever
Content-Type: application/json
```

```json
{
  "speed_sp": 250,
  "stop_action": "brake"
}
```

The command returns after it is submitted to the EV3 driver. A later `stop`
request is required to stop continuous movement.

### Run to relative position

```http
POST /api/motors/{code}/run-to-rel-pos
Content-Type: application/json
```

```json
{
  "speed_sp": 300,
  "position_sp": 360,
  "stop_action": "hold"
}
```

`position_sp` is an encoder-relative position in degrees as interpreted by the
EV3 motor driver.

### Reset

```http
POST /api/motors/{code}/reset
Content-Type: application/json
```

An empty JSON object may be used as the request body.

## Motor parameter validation

- `speed_sp` must be a non-zero integer between `-2000` and `2000`;
- `time_sp` must be an integer between `1` and `600000` milliseconds;
- `position_sp` must be an integer with absolute value no greater than `1000000`;
- optional `stop_action` must be `coast`, `brake` or `hold`;
- the request body must be a JSON object and is limited to 8192 bytes.

These are application-boundary checks for this increment. Device-specific
limits remain enforced by the EV3 driver and are strengthened by later safety
commits.

## Execution model

Motor operations are executed immediately. The API does **not** yet expose:

- `command_id` or command history;
- queues or priorities;
- cancellation of pending work;
- synchronized multi-motor batches;
- watchdog/timeout supervision for continuous movement;
- differential drive or navigation;
- authentication/tokens.

If the configured motor cannot be connected or the EV3 driver rejects the
operation, the API returns `503 Service Unavailable` and retains the driver
error internally in the motor snapshot.

## Application lifecycle

`RoverApplication` continues to own startup and orderly shutdown. Remote
shutdown/restart is not exposed by the REST API in this increment.
