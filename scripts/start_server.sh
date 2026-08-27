#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
exec /usr/local/bin/python3 server.py
