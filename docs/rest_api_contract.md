# Rover-DR REST API Contract

## Overview

This increment replaces immediate motor execution with asynchronous command orchestration. Read endpoints remain available, while movement requests are admitted into independent motor queues and receive persistent command identifiers.

### Base URL

```text
http://<host>:8080
```

Default bind address: `0.0.0.0`. Default TCP port: `8080`.

## Common response format

Successful query:

```json
{
  "success": true,
  "status_code": 200,
  "data": {}
}
```

Queued command:

```json
{
  "success": true,
  "status_code": 202,
  "data": {
    "accepted": true,
    "command_id": 12,
    "status": "QUEUED",
    "priority": 80
  }
}
```

Errors use the same envelope with `success: false` and an `error` field.

## HTTP status codes

| Status | Meaning |
| --- | --- |
| `200 OK` | Query, cancellation or immediate stop completed. |
| `202 Accepted` | Motor command or synchronized batch admitted to the queue. |
| `204 No Content` | Successful `OPTIONS` preflight. |
| `400 Bad Request` | Invalid JSON, route parameter or command parameter. |
| `404 Not Found` | Endpoint, motor or command identifier does not exist. |
| `405 Method Not Allowed` | Unsupported HTTP method. |
| `500 Internal Server Error` | Unexpected REST processing failure. |
| `503 Service Unavailable` | Required application port or motor backend is unavailable. |

## Read endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | REST API availability. |
| GET | `/api/rover/state` | Consolidated Rover snapshot. |
| GET | `/api/sensors` | Lists sensors. |
| GET | `/api/sensors/all` | Complete sensor snapshots. |
| GET | `/api/sensors/{code}` | One sensor snapshot. |
| GET | `/api/motors` | Lists motors with queue metadata. |
| GET | `/api/motors/all` | Complete motor snapshots. |
| GET | `/api/motors/{code}` | One motor snapshot. |
| GET | `/api/motor-commands` | Lists all command lifecycle records. |
| GET | `/api/motor-commands/{id}` | Reads one command lifecycle record. |
| GET | `/api/motors/{code}/commands` | Lists command records for one motor. |
| GET | `/api/controller/status` | General controller status. |
| GET | `/api/controller/network` | Network information. |
| GET | `/api/controller/battery` | Battery information. |
| GET | `/api/controller/system` | System information. |

## Queue model

Each configured motor owns an independent priority queue and worker thread. A command admitted to a queue receives a monotonic `command_id` and transitions through the following public states:

```text
QUEUED -> RUNNING -> COMPLETED
                  -> FAILED
       -> CANCELLED
```

Priorities are integers from `0` to `100`. Higher numeric values execute first. Commands with the same priority preserve FIFO admission order.

A command already running is not displaced by a later higher-priority request. Priority controls the order of **pending** work.

## Queued motor operations

### Run timed

```http
POST /api/motors/{code}/run-timed
Content-Type: application/json
```

```json
{
  "speed_sp": 300,
  "time_sp": 1000,
  "priority": 70,
  "stop_action": "brake"
}
```

### Run forever

```http
POST /api/motors/{code}/run-forever
Content-Type: application/json
```

```json
{
  "speed_sp": 250,
  "priority": 50,
  "stop_action": "brake"
}
```

A `run-forever` command remains `RUNNING` until cancelled, stopped or terminated by the configured watchdog.

### Run to relative position

```http
POST /api/motors/{code}/run-to-rel-pos
Content-Type: application/json
```

```json
{
  "speed_sp": 300,
  "position_sp": 360,
  "priority": 60,
  "stop_action": "hold"
}
```

### Reset

```http
POST /api/motors/{code}/reset
Content-Type: application/json
```

```json
{"priority": 10}
```

## Cancellation and stop

Cancel queued and active work for one motor:

```http
POST /api/motors/{code}/cancel
Content-Type: application/json

{}
```

The response contains `cancelled_command_ids`.

`POST /api/motors/{code}/stop` is intentionally preemptive. It cancels pending work for the motor, requests physical stop immediately and creates its own completed/failed command lifecycle record.

## Synchronized multi-motor batch

```http
POST /api/motors/synchronized
Content-Type: application/json
```

```json
{
  "priority": 80,
  "commands": [
    {
      "code": "LLM",
      "action": "run-timed",
      "speed_sp": 300,
      "time_sp": 1000,
      "stop_action": "brake"
    },
    {
      "code": "RLM",
      "action": "run-timed",
      "speed_sp": 300,
      "time_sp": 1000,
      "stop_action": "brake"
    }
  ]
}
```

Supported batch actions in this increment are `run-timed`, `run-forever` and `run-to-rel-pos`. A batch may contain only one command per motor.

The server assigns a shared `batch_id` and `scheduled_start_at` timestamp. Independent motor workers wait for that common timestamp before dispatch. This is best-effort software synchronization; hard real-time guarantees are outside the scope of this increment.

## Parameter validation

- `speed_sp`: non-zero integer from `-2000` through `2000`;
- `time_sp`: integer from `1` through `600000` milliseconds;
- `position_sp`: integer with absolute value no greater than `1000000`;
- `priority`: integer from `0` through `100`;
- `stop_action`: `coast`, `brake` or `hold`;
- `timeout_ms`: optional integer from `100` through `600000` milliseconds;
- `watchdog_ms`: optional integer from `100` through `600000` milliseconds for `run-forever`;
- request body: JSON object no larger than 8192 bytes.


## Differential drive

This increment introduces a drive-level abstraction above individual motor
commands. The configured traction pair is `LLM` (left) and `RLM` (right).
The drive service does not access `ev3dev2` directly; it delegates to the
existing motor port and synchronized command machinery.

### Drive status

```http
GET /api/drive/status
```

Returns the configured traction motor codes, current motor snapshots, gyroscope
angle, calibration data, estimated pose and the last drive-level request.

### Tank control

```http
POST /api/drive/tank
Content-Type: application/json
```

```json
{
  "left_speed_sp": 300,
  "right_speed_sp": 250,
  "priority": 60,
  "watchdog_ms": 2000,
  "stop_action": "brake"
}
```

`left_speed_sp` and `right_speed_sp` are independent signed EV3 speed
setpoints in the range `-2000` through `2000`. Zero is accepted at drive level
so one side may remain stationary during a pivot. The pair is submitted as a
synchronized `run-forever` batch and therefore normally returns `202 Accepted`
with a shared `batch_id`. If both speeds are zero, the request is treated as a
drive stop.

### Stop differential drive

```http
POST /api/drive/stop
Content-Type: application/json
```

```json
{
  "stop_action": "brake"
}
```

The stop operation preempts pending work for both traction motors and requests
an immediate safe stop on each side.

## Odometry, gyroscope and basic navigation

The drive status now includes `pose` (`x_mm`, `y_mm`, `heading_deg`,
`distance_mm`) and `gyro_angle_deg`. Encoder deltas feed differential-drive
odometry; when the configured `GYR` sensor is available its angle is used as
the current heading estimate.

### Reset odometry

```http
POST /api/drive/reset-odometry
Content-Type: application/json
```

```json
{"x_mm": 0, "y_mm": 0, "heading_deg": 0}
```

### Move a linear distance

```http
POST /api/drive/move-distance
Content-Type: application/json
```

```json
{"distance_mm": 250, "speed_sp": 300, "stop_action": "brake"}
```

### Rotate in place

```http
POST /api/drive/rotate-angle
Content-Type: application/json
```

```json
{"angle_deg": 90, "speed_sp": 250, "stop_action": "brake"}
```

### Drive an arc

```http
POST /api/drive/curve-radius
Content-Type: application/json
```

```json
{"radius_mm": 250, "angle_deg": 45, "speed_sp": 300, "stop_action": "brake"}
```

Finite navigation operations return `202 Accepted` with the synchronized
`batch_id` and the two underlying motor `command_ids`. They are geometric,
encoder-targeted motions; closed-loop path correction and autonomous path
planning remain deferred.

## Deliberately deferred capabilities

This increment still does **not** provide advanced closed-loop navigation,
autonomous path planning, the expanded `ev3dev2.motor` gateway or
authentication/tokens. Those capabilities remain reserved for later commits.

## Motor safety supervision

Movement commands are supervised after queue admission. The optional `timeout_ms`
parameter overrides the general execution deadline for bounded commands.
`run-forever` additionally accepts `watchdog_ms`; if it is omitted, the centralized
`motor_run_forever_watchdog_ms` value is used. Safety decisions use a monotonic
clock. A command can finish as `TIMED_OUT` or `STALLED`; in both cases the service
issues a safe motor stop before publishing the final command state.

Example:

```json
{
  "speed_sp": 300,
  "watchdog_ms": 2000,
  "stop_action": "brake",
  "priority": 50
}
```

Accepted safety timeout values range from 100 to 600000 milliseconds.
