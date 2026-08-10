#!/bin/bash

set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <project-name>"
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_DIR="/home/robot/${PROJECT_NAME}"
ENV_FILE="/home/robot/.rover.env"
MAIN_FILE="${PROJECT_DIR}/main.py"

if [ ! -d "${PROJECT_DIR}" ]; then
    echo "Application error: ${PROJECT_DIR} not found."
    exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
    echo "Configuration error: ${ENV_FILE} not found."
    exit 1
fi

if [ ! -f "${MAIN_FILE}" ]; then
    echo "Application error: ${MAIN_FILE} not found."
    exit 1
fi

cd "${PROJECT_DIR}"

. "${ENV_FILE}"

exec /usr/bin/python3 "${MAIN_FILE}"
