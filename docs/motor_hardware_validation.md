# EV3 motor hardware validation checklist

This increment introduces read-only access to physical EV3 motors through
`python-ev3dev2`. The following checks validate the integration without moving
the Rover.

1. Secure the Rover and keep all wheels clear of obstacles.
2. Confirm the configured ports in `config/rover_config.json`:
   - `LLM` -> `outA` (`LargeMotor`)
   - `LMM` -> `outB` (`MediumMotor`)
   - `RMM` -> `outC` (`MediumMotor`)
   - `RLM` -> `outD` (`LargeMotor`)
3. Confirm the configured polarity of each motor before any later movement test.
4. Start Rover-DR on the EV3 and request `GET /api/motors/all`.
5. Confirm that each physically connected motor reports `connected: true`.
6. Confirm that `driver_name`, `max_speed`, `position`, `speed`, `duty_cycle`,
   `state` and `polarity` reflect the EV3 driver values.
7. Disconnect one motor, wait at least one monitoring cycle and confirm that
   the API reports `connected: false` together with an error description.
8. Reconnect the motor and confirm that a later monitoring cycle discovers it
   again.
9. Run the application on a development computer without EV3 hardware and
   confirm that startup remains successful and motors are reported as
   unavailable instead of terminating the process.

No movement command is part of this increment. Motor execution is introduced
in the next commit.

## Basic command validation (Commit 9)

After confirming that each configured motor is detected, validate the new
immediate execution routes one motor at a time with the Rover lifted so that
wheels cannot propel the chassis unexpectedly.

Recommended sequence for each motor:

1. `POST /api/motors/{code}/reset` with `{}`;
2. `POST /api/motors/{code}/run-timed` using a low `speed_sp` and short `time_sp`;
3. verify encoder position through `GET /api/motors/{code}`;
4. `POST /api/motors/{code}/run-to-rel-pos` with a small target;
5. `POST /api/motors/{code}/run-forever` at low speed;
6. immediately issue `POST /api/motors/{code}/stop`;
7. confirm that `state` no longer reports the motor as running.

This increment has no watchdog for `run-forever`. Continuous movement must
therefore be tested only under direct operator supervision. Watchdog and motor
safety mechanisms are introduced in a later commit.
