#!/bin/bash

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="/home/robot"

echo "Installing Rover-DR EV3 launcher files..."

install -m 755 \
    "${SCRIPT_DIR}/01-start-by-EV3.sh" \
    "${TARGET_DIR}/01-start-by-EV3.sh"

install -m 755 \
    "${SCRIPT_DIR}/02-start-by-VSCode.sh" \
    "${TARGET_DIR}/02-start-by-VSCode.sh"

install -m 755 \
    "${SCRIPT_DIR}/03-start-rover-project.sh" \
    "${TARGET_DIR}/03-start-rover-project.sh"

if [ -f "${SCRIPT_DIR}/.rover.env" ]; then
    if [ -f "${TARGET_DIR}/.rover.env" ]; then
        echo "Configuration preserved: ${TARGET_DIR}/.rover.env already exists."
    else
        install -m 600 \
            "${SCRIPT_DIR}/.rover.env" \
            "${TARGET_DIR}/.rover.env"

        echo "Configuration installed: ${TARGET_DIR}/.rover.env"
    fi
else
    echo "Warning: ${SCRIPT_DIR}/.rover.env not found."
fi

echo "Rover-DR EV3 launcher installation completed."
