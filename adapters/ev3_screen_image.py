#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Minimal EV3 PBM screen loader used by the graphical mode selector.

This first screen abstraction deliberately performs a direct disk load. The
runtime memory cache and the complete PBM asset catalogue are introduced in a
later increment.
"""

import os


EV3_SCREEN_WIDTH = 178
EV3_SCREEN_HEIGHT = 128
EV3_SCREEN_SIZE = (EV3_SCREEN_WIDTH, EV3_SCREEN_HEIGHT)


def screen_assets_path():
    """Returns the directory containing the currently deployed EV3 screens."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "assets", "screens")


def screen_asset_path(filename):
    """Returns the absolute path for one named EV3 screen asset."""
    return os.path.join(screen_assets_path(), filename)


def load_monochrome_screen(asset_path, screen_name="EV3 screen"):
    """Loads and validates one ready-to-display monochrome PBM screen."""
    from PIL import Image  # pylint: disable=import-error

    source = Image.open(asset_path)
    try:
        source.load()
        if source.mode != "1":
            raise ValueError(
                "{0} must be a 1-bit monochrome PBM image".format(screen_name)
            )
        if source.size != EV3_SCREEN_SIZE:
            raise ValueError(
                "{0} must be {1}x{2} pixels".format(
                    screen_name,
                    EV3_SCREEN_WIDTH,
                    EV3_SCREEN_HEIGHT
                )
            )
        return source.copy()
    finally:
        source.close()
