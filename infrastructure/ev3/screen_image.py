#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared direct loading and in-memory reuse of EV3 PBM screen assets."""

import hashlib
import os
import threading


EV3_SCREEN_WIDTH = 178
EV3_SCREEN_HEIGHT = 128
EV3_SCREEN_SIZE = (EV3_SCREEN_WIDTH, EV3_SCREEN_HEIGHT)

SCREEN_CACHE_DIRECTORY_NAME = "cache"

_CACHE_LOCK = threading.RLock()
_MEMORY_CACHE = {}


def load_monochrome_screen(asset_path, screen_name="EV3 screen"):
    """Loads one ready-to-use 1-bit PBM screen from disk or memory."""
    background, unused_source = _load_monochrome_screen(
        asset_path,
        screen_name
    )
    del unused_source
    return background


def warm_monochrome_screen_cache(screens_path=None):
    """Preloads every PBM file already available in the screen cache."""
    active_path = screens_path or default_screen_cache_path()
    result = {
        "total": 0,
        "memory_hits": 0,
        "loaded": 0,
        "failed": []
    }

    try:
        filenames = sorted(
            filename for filename in os.listdir(active_path)
            if filename.lower().endswith(".pbm")
        )
    except (IOError, OSError) as error:
        result["failed"].append((active_path, str(error)))
        return result

    result["total"] = len(filenames)
    for filename in filenames:
        asset_path = os.path.join(active_path, filename)
        try:
            background, source = _load_monochrome_screen(
                asset_path,
                filename
            )
            background.close()
            result[source] += 1
        except (
                ImportError, IOError, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            result["failed"].append((filename, str(error)))
    return result


def default_screen_assets_path():
    """Returns the project screen-assets directory."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))
    return os.path.join(project_root, "assets", "screens")


def default_screen_cache_path():
    """Returns the directory containing deployable PBM screen assets."""
    return os.path.join(
        default_screen_assets_path(),
        SCREEN_CACHE_DIRECTORY_NAME
    )


def cached_screen_path(filename):
    """Returns the absolute path of one PBM asset in the screen cache."""
    return os.path.join(default_screen_cache_path(), filename)


def clear_monochrome_screen_memory_cache():
    """Closes and removes process-memory screen entries, primarily for tests."""
    with _CACHE_LOCK:
        for entry in _MEMORY_CACHE.values():
            entry["image"].close()
        _MEMORY_CACHE.clear()


def _load_monochrome_screen(asset_path, screen_name):
    from PIL import Image  # pylint: disable=import-error

    source_path = os.path.abspath(asset_path)
    source_state = _read_source_state(source_path)

    with _CACHE_LOCK:
        memory_image = _load_memory_image(source_path, source_state)
        if memory_image is not None:
            return memory_image, "memory_hits"

        background = _open_valid_pbm(Image, source_path, screen_name)
        _store_memory_image(source_path, source_state, background)
        return background.copy(), "loaded"


def _read_source_state(source_path):
    source_stat = os.stat(source_path)
    mtime_ns = getattr(
        source_stat,
        "st_mtime_ns",
        int(source_stat.st_mtime * 1000000000)
    )
    ctime_ns = getattr(
        source_stat,
        "st_ctime_ns",
        int(source_stat.st_ctime * 1000000000)
    )
    return {
        "size": source_stat.st_size,
        "mtime_ns": mtime_ns,
        "ctime_ns": ctime_ns,
        "sha256": _sha256_file(source_path)
    }


def _sha256_file(source_path):
    """Returns a deterministic content signature for one small PBM asset."""
    digest = hashlib.sha256()
    with open(source_path, "rb") as source_file:
        while True:
            chunk = source_file.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_memory_image(source_path, source_state):
    entry = _MEMORY_CACHE.get(source_path)
    if entry is None:
        return None
    if entry["source_size"] != source_state["size"]:
        return None
    if entry["source_mtime_ns"] != source_state["mtime_ns"]:
        return None
    if entry["source_ctime_ns"] != source_state["ctime_ns"]:
        return None
    if entry["source_sha256"] != source_state["sha256"]:
        return None
    return entry["image"].copy()


def _open_valid_pbm(Image, source_path, screen_name):
    source_image = Image.open(source_path)
    try:
        source_image.load()
        if source_image.mode != "1":
            raise ValueError(
                "{0} must be a 1-bit monochrome PBM image".format(
                    screen_name
                )
            )
        if source_image.size != EV3_SCREEN_SIZE:
            raise ValueError(
                "{0} must be {1}x{2} pixels".format(
                    screen_name,
                    EV3_SCREEN_WIDTH,
                    EV3_SCREEN_HEIGHT
                )
            )
        return source_image.copy()
    finally:
        source_image.close()


def _store_memory_image(source_path, source_state, background):
    previous = _MEMORY_CACHE.get(source_path)
    if previous is not None:
        previous["image"].close()
    _MEMORY_CACHE[source_path] = {
        "source_size": source_state["size"],
        "source_mtime_ns": source_state["mtime_ns"],
        "source_ctime_ns": source_state["ctime_ns"],
        "source_sha256": source_state["sha256"],
        "image": background.copy()
    }
