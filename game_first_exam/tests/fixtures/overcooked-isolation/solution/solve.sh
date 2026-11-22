#!/bin/sh
set -eu
test "$(id -u)" = 65534
test "$(awk '/^CapEff:/ {print $2}' /proc/self/status)" = 0000000000000000
test "$(awk '/^NoNewPrivs:/ {print $2}' /proc/self/status)" = 1
for path in /tests /data /srv/instance.json /srv/adapter.py /var/run/docker.sock; do
  test ! -e "$path"
done
# Reject extra workspace, engine, evidence and host mounts in the agent's namespace.
awk '$5 != "/" && $5 !~ /^\/(proc|sys|dev)(\/|$)/ &&
     $5 !~ /^\/etc\/(hosts|hostname|resolv\.conf)$/ &&
     $5 !~ /^\/logs\/(agent|artifacts|verifier)$/ {print "unexpected mount:", $5; exit 1}' /proc/self/mountinfo
# The trial network is internal. The public client must still reach sim by service name.
awk 'NR > 1 && $2 == "00000000" {exit 1}' /proc/net/route
python /app/overcooked_probe.py
# Harbor shares this log directory between phases and clears it before verification.
touch /logs/verifier/agent-stage-marker
hostname > /logs/artifacts/agent-hostname.txt
