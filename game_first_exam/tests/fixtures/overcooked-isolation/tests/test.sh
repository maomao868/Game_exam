#!/bin/sh
set -eu
# Check Harbor's own pre-verifier cleanup before writing anything to its log directory.
test ! -e /logs/verifier/agent-stage-marker
test ! -e /solution/solve.sh
test ! -e /srv/instance.json
test ! -e /var/run/docker.sock
test "$(ls /sys/class/net)" = lo
test -f /data/collection.ready
agent=$(cat /logs/artifacts/agent-hostname.txt)
sim=$(cat /data/sim-hostname.txt)
verifier=$(hostname)
test "$agent" != "$sim"
test "$agent" != "$verifier"
test "$sim" != "$verifier"
sha256sum /data/final.json > /logs/verifier/evidence.sha256
python /tests/grade.py
echo "$verifier" > /logs/verifier/verifier-hostname.txt
