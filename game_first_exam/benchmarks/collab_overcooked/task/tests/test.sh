#!/bin/sh
set -eu
test "$(ls /sys/class/net)" = lo
test ! -e /solution
test ! -e /status
test ! -e /role
test ! -e /run/secrets/model_key
test ! -e /var/run/docker.sock
test ! -e /logs/verifier/agent-marker
cd /bench/src
python /integration/grade.py
