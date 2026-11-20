#!/usr/bin/env bash
# Use a new internal network, with no host ports or shared volumes.
set -euo pipefail
network="towermind-test-$$-$RANDOM"
sim="$network-sim"
cleanup() {
  docker rm -f "$sim" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
docker network create --internal "$network" >/dev/null
trap cleanup EXIT
docker run -d --init --name "$sim" --network "$network" --network-alias sim \
  "${1:-game-tests:towermind}" >/dev/null
if ! docker run --rm --network "$network" "${2:-game-tests:towermind-client}"; then
  docker inspect --format '{{.State.Status}} (exit {{.State.ExitCode}}), command {{json .Config.Cmd}}' "$sim"
  docker logs "$sim"
  exit 1
fi
