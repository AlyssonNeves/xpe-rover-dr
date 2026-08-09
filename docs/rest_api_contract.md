# Rover-DR REST API Contract

## Overview

This increment introduces the first Rover-DR HTTP/JSON interface. The API is
read-only and exposes the monitoring information implemented in the previous
increment.

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

## Health

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Returns basic REST API availability. |

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

## Scope of this increment

The API intentionally contains no motor execution commands, navigation,
sensor-mode changes, lifecycle operations, authentication, tokens or global
hardware configuration. Those capabilities are introduced in later commits.
