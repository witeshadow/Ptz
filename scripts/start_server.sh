#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
exec /usr/bin/env python3 server.py
