# EV3Dev2 Motor Domain Coverage

## 1. Supported Scope

Rover DR deliberately adopts a scope restricted to the LEGO EV3 motors used by the project:

* `LargeMotor`;
* `MediumMotor`.

The functional coverage of these two classes includes public methods inherited from `Motor`, readable and writable properties, speed values, and native commands supported by `python-ev3dev2` 2.1.0.post1.

The movement domain also includes:

* `MotorSet`;
* `MoveTank`;
* `MoveSteering`;
* `MoveJoystick`;
* `MoveDifferential`.

Classes outside this scope are rejected by the gateway.

## 2. Domain Integration

### 2.1 LargeMotor and MediumMotor

`LargeMotor` and `MediumMotor` objects may only be created when the physical address corresponds to a motor configured in Rover. Every operation capable of modifying the hardware is executed through `MotorPort.execute_guarded_operation`.

The guarded operation:

1. validates the motor codes;
2. preempts pending and active commands;
3. reserves the motors during execution;
4. prevents new concurrent commands;
5. executes the native EV3Dev2 call;
6. applies a safe stop in case of failure;
7. records the operation for audit purposes.

### 2.2 Properties

Properties may be read directly. Writing is only accepted when the official descriptor provides a setter, and it always passes through the domain's guarded operation.

### 2.3 MotorSet, MoveTank, MoveSteering, MoveJoystick, and MoveDifferential Are Integrated into the Domain

These classes are no longer exposed solely through reflection. Each instance is bound to Rover's configured motors, and its physical methods are executed through the same safety boundary applied to `LargeMotor` and `MediumMotor`.

This ensures that operations such as tank movement, steering, joystick control, odometry, turns, rotation, line following, and gyroscope-assisted following do not bypass:

* command preemption;
* exclusive motor reservation;
* safe stopping;
* concurrency control;
* operational auditing.

## 3. Gateway Correction

The `/api/ev3dev2/motor/*` endpoints remain available; however, the gateway is no longer generic and reflective for every public class.

The gateway now:

* accepts only classes within Rover's supported scope;
* requires a `MotorPort` implementation;
* binds each object to the configured motors;
* routes physical calls through `execute_guarded_operation`;
* rejects objects that do not match configured addresses;
* rejects writes to attributes that are not writable properties;
* keeps the catalog restricted to the supported domain.

Therefore, the endpoints no longer provide a direct path for commanding hardware outside `MotorMonitor`.

## 4. Endpoints

| Operation                  | Endpoint                                                     |
| -------------------------- | ------------------------------------------------------------ |
| Supported-scope catalog    | `GET /api/ev3dev2/motor/catalog`                             |
| Allowed constant or member | `GET /api/ev3dev2/motor/members/{name}`                      |
| List managed objects       | `GET /api/ev3dev2/motor/objects`                             |
| Create supported object    | `POST /api/ev3dev2/motor/objects`                            |
| Invoke guarded method      | `POST /api/ev3dev2/motor/objects/{id}/methods/{method}`      |
| Read property              | `GET /api/ev3dev2/motor/objects/{id}/properties/{property}`  |
| Write guarded property     | `POST /api/ev3dev2/motor/objects/{id}/properties/{property}` |
| Release object             | `DELETE /api/ev3dev2/motor/objects/{id}`                     |

## 5. Verification Limit

Software coverage is complete for the declared scope. Final validation of behavior, accuracy, synchronization, braking, ramping, stall detection, gyroscope operation, and odometry still depends on testing with actual EV3 hardware.
::: 
