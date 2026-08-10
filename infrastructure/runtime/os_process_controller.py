#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Operating-system process controller."""

import os
import sys

from ports.process_control_port import ProcessControlPort


class OsProcessController(ProcessControlPort):
    def restart_current_process(self):
        os.execv(sys.executable, [sys.executable] + sys.argv)
