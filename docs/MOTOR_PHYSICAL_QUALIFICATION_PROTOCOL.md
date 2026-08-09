# EV3 motor physical qualification protocol

## Scope

This protocol qualifies the safety-managed motor domain for `LargeMotor`,
`MediumMotor`, `MotorSet`, `MoveTank`, `MoveSteering`, `MoveJoystick` and
`MoveDifferential` on an EV3 running `python-ev3dev2==2.1.0.post1`.

## Required evidence

Record the EV3 image, kernel, Python version, python-ev3dev2 version, motor model,
ports, supply voltage, wheel geometry, load, configuration file and test operator.
For every test retain REST request/response, Rover log, encoder telemetry and video.

## Test matrix

| ID | Test | Acceptance criteria |
|---|---|---|
| PHY-01 | LargeMotor bounded and continuous commands | Direction, speed, encoder and stop behavior match the request; watchdog stops continuous motion. |
| PHY-02 | MediumMotor bounded and continuous commands | Same criteria as PHY-01 using the configured MediumMotor limits. |
| PHY-03 | Ramp-up and ramp-down | Measured acceleration/deceleration is progressive and remains within configured timing tolerance. |
| PHY-04 | coast, brake and hold | Each stop action produces observably distinct and repeatable behavior; hold maintains position without unsafe oscillation. |
| PHY-05 | Stall detection | A controlled obstruction produces STALLED, stops power and releases the operation reservation. |
| PHY-06 | Duty cycle | `run_direct` respects -100..100 and the configured dynamic limit; watchdog stops the motor. |
| PHY-07 | MotorSet synchronization | All configured ports start and stop together; no partially unknown port is accepted. |
| PHY-08 | MoveTank/MoveSteering/MoveJoystick | Continuous and bounded movement remains registered until physical stop or completion. |
| PHY-09 | follow_line | Controlled course completion without leaving a background operation or motor reservation active. |
| PHY-10 | follow_gyro_angle | Heading error remains inside the project tolerance and emergency stop interrupts immediately. |
| PHY-11 | MoveDifferential odometry | `odometry_start` remains active; `odometry_stop`, deletion and shutdown stop the service safely. |
| PHY-12 | Curves and coordinates | Radius, turn angle and coordinate destination remain inside calibrated tolerance. |
| PHY-13 | Emergency stop | All active objects, background services and motors stop within the project safety limit. |
| PHY-14 | Concurrent Rover versus gateway command | The second command is rejected while the same motor is reserved. |
| PHY-15 | Partial two-motor failure | Both motors are stopped and the operation ends FAILED without a residual reservation. |

## Execution commands

Install the pinned driver and execute the complete contract suite:

```bash
python3 -m pip install python-ev3dev2==2.1.0.post1
pytest -q tests/unit/test_ev3dev2_motor_real_api.py
pytest -q
```

## Approval

Coverage may be declared physically qualified only after all tests pass and the
evidence package is reviewed. Unit tests alone do not constitute hardware proof.
