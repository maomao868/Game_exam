#!/bin/sh
set -eu
test "$(id -u)" = 65534
test "$(ls /sys/class/net)" = lo
for path in /bench /evidence /tests /channels /role /var/run/docker.sock /run/secrets/model_key; do test ! -e "$path"; done
test ! -w /status
touch /logs/verifier/agent-marker
while [ ! -s /status/state ]; do sleep 1; done
test "$(cat /status/state)" = complete
