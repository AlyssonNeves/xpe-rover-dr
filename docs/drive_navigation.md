# Differential Drive Navigation

Commit 13 adds basic geometric navigation, encoder odometry and EV3 gyroscope
feedback above the existing differential-drive abstraction.

## Calibration

The `drive` section of `config/rover_config.json` defines:

- `left_motor_code` and `right_motor_code`;
- `gyro_sensor_code`;
- `wheel_diameter_mm`;
- `track_width_mm`;
- optional left/right speed factors.

The current baseline uses 56 mm wheels and a 120 mm track width. These values
must be measured on the physical Rover before precision tests.

## Odometry

`GET /api/drive/status` returns an estimated pose:

```json
{
  "x_mm": 0.0,
  "y_mm": 0.0,
  "heading_deg": 0.0,
  "distance_mm": 0.0
}
```

Encoder deltas are converted to wheel travel and integrated as differential-drive
odometry. When a valid gyroscope reading is available, it replaces the encoder-
derived heading estimate for the current pose.

Odometry can be reset with `POST /api/drive/reset-odometry`.

## Basic navigation

The service supports three finite geometric motions:

- straight displacement (`move-distance`);
- in-place rotation (`rotate-angle`);
- circular arc (`curve-radius`).

Each operation is converted into relative wheel encoder targets and submitted as
a synchronized motor batch. This is intentionally basic open-loop geometric
navigation. Closed-loop trajectory correction, autonomous path planning and
advanced recovery remain outside this increment.

## Gyroscope availability

The sensor monitor attempts to connect the configured `GYR` sensor using
`ev3dev2.sensor.lego.GyroSensor`. If EV3 hardware or the library is unavailable,
the application remains operational and reports the gyroscope as disconnected.
