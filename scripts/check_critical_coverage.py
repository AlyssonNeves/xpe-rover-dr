#!/usr/bin/env python3
"""Enforce branch-aware coverage floors for safety-critical modules."""

import json
import sys


GLOBAL_MINIMUM = 70.0


THRESHOLDS = {
    "adapters/out_ev3_gyro_sensor.py": 75.0,
    "adapters/out_heading_state.py": 80.0,
    "app/services/manual_drive_service.py": 65.0,
    "app/services/joystick_control_service.py": 70.0,
    "adapters/in_rest_api_server.py": 65.0,
    "bootstrap/rover_assembly.py": 65.0,
    "infrastructure/monitoring/gyro_heading_monitor.py": 70.0,
    "infrastructure/monitoring/motor_monitor.py": 65.0,
    "infrastructure/state/heading_state_store.py": 80.0,
    "infrastructure/motor/command_executor.py": 80.0,
    "infrastructure/motor/command_scheduler.py": 60.0,
    "infrastructure/motor/state_collector.py": 80.0,
    "infrastructure/motor/guarded_operation_manager.py": 80.0,
    "infrastructure/motor/safety_watchdog.py": 80.0,
    "infrastructure/motor/synchronized_executor.py": 80.0
}


def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else "coverage.json"
    with open(report_path, "r") as report_file:
        report = json.load(report_file)
    failures = []
    total_actual = float(report.get("totals", {}).get("percent_covered", 0.0))
    print("Global combined line/branch coverage: {0:.1f}% (minimum {1:.1f}%)".format(
        total_actual, GLOBAL_MINIMUM
    ))
    if total_actual + 0.00001 < GLOBAL_MINIMUM:
        failures.append(("TOTAL", total_actual, GLOBAL_MINIMUM, "below"))
    for module_path, minimum in sorted(THRESHOLDS.items()):
        module = report.get("files", {}).get(module_path)
        if module is None:
            failures.append((module_path, 0.0, minimum, "missing"))
            continue
        actual = float(module["summary"]["percent_covered"])
        if actual + 0.00001 < minimum:
            failures.append((module_path, actual, minimum, "below"))
        print("{0}: {1:.1f}% (minimum {2:.1f}%)".format(
            module_path, actual, minimum
        ))
    if failures:
        for module_path, actual, minimum, reason in failures:
            print(
                "Coverage gate failed for {0}: {1:.1f}% < {2:.1f}% ({3}).".format(
                    module_path, actual, minimum, reason
                )
            )
        return 1
    print("Critical-module coverage gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
