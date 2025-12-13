#!/usr/bin/env sh
set -e

if [ "$1" = "test" ]; then
  shift
  exec pytest -s tests/test_live_coach.py "$@"
fi

exec "$@"
