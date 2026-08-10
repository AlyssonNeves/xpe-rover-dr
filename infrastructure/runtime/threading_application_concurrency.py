#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Threading implementation of application concurrency primitives."""

import threading

from ports.application_concurrency_port import ApplicationConcurrencyPort


class ThreadingApplicationConcurrency(ApplicationConcurrencyPort):
    def __init__(self):
        self._lifecycle_lock = threading.Lock()
        self._stop_completed = threading.Event()
        self._stop_requested = False
        self._lifecycle_request_claimed = False
        self._restart_requested = False

    def claim_stop(self):
        with self._lifecycle_lock:
            if self._stop_requested:
                return False
            self._stop_requested = True
            return True

    def is_stop_requested(self):
        with self._lifecycle_lock:
            return self._stop_requested

    def wait_for_stop_completed(self, timeout_seconds):
        return self._stop_completed.wait(timeout=timeout_seconds)

    def mark_stop_completed(self):
        self._stop_completed.set()

    def claim_shutdown_request(self):
        return self._claim_lifecycle_request(restart_requested=False)

    def claim_restart_request(self):
        return self._claim_lifecycle_request(restart_requested=True)

    def _claim_lifecycle_request(self, restart_requested):
        with self._lifecycle_lock:
            if self._lifecycle_request_claimed or self._stop_requested:
                return False
            self._lifecycle_request_claimed = True
            self._restart_requested = bool(restart_requested)
            return True

    def is_restart_requested(self):
        with self._lifecycle_lock:
            return self._restart_requested

    def claim_critical_shutdown(self):
        return self.claim_shutdown_request()

    def run_async(self, target, name, daemon):
        thread = threading.Thread(target=target, name=name)
        thread.daemon = bool(daemon)
        thread.start()
        return thread

    @staticmethod
    def is_current_component(component):
        return component is threading.current_thread()
