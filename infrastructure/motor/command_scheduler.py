#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Per-motor priority scheduling and worker lifecycle."""

import queue
import threading


class MotorCommandScheduler(object):
    """Owns command queues, cancellation metadata and worker threads."""

    def __init__(self, motor_codes, command_executor):
        self._executor = command_executor
        self._queues = dict(
            (code, queue.PriorityQueue()) for code in motor_codes
        )
        self._tracked = {}
        self._lock = threading.RLock()
        self._sequence = 0
        self._workers = {}
        self._stop_event = threading.Event()

    def next_id(self):
        with self._lock:
            self._sequence += 1
            return self._sequence

    def enqueue(self, command):
        motor_code = command["motor_code"]
        with self._lock:
            self._tracked.setdefault(motor_code, []).append(command)
            self._queues[motor_code].put(
                (command["priority"], command["id"], command)
            )

    def size(self, motor_code):
        with self._lock:
            return len([
                item for item in self._tracked.get(motor_code, [])
                if not item.get("cancelled")
            ])

    def cancel(self, motor_code):
        count = 0
        with self._lock:
            for command in self._tracked.get(motor_code, []):
                if not command.get("cancelled"):
                    command["cancelled"] = True
                    count += 1
        return count

    def remove(self, command):
        motor_code = command["motor_code"]
        with self._lock:
            self._tracked[motor_code] = [
                item for item in self._tracked.get(motor_code, [])
                if item["id"] != command["id"]
            ]

    def process_available(self, motor_code):
        motor_queue = self._queues[motor_code]
        while not motor_queue.empty():
            try:
                _, _, command = motor_queue.get_nowait()
            except queue.Empty:
                return
            self._execute_and_release(motor_queue, command)

    def start(self):
        self._stop_event.clear()
        for motor_code in self._queues:
            worker = threading.Thread(
                target=self._worker_loop,
                args=(motor_code,),
                name="MotorWorker-{0}".format(motor_code)
            )
            worker.daemon = True
            worker.start()
            self._workers[motor_code] = worker

    def stop(self, timeout_seconds=0.5):
        self._stop_event.set()
        for worker in self._workers.values():
            worker.join(timeout_seconds)

    def _worker_loop(self, motor_code):
        motor_queue = self._queues[motor_code]
        while not self._stop_event.is_set():
            try:
                _, _, command = motor_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self._execute_and_release(motor_queue, command)

    def _execute_and_release(self, motor_queue, command):
        try:
            if not command.get("cancelled"):
                self._executor(command)
        finally:
            self.remove(command)
            motor_queue.task_done()
