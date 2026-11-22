#!/usr/bin/env bash
set -euo pipefail
network="overcooked-test-$$-$RANDOM"
sim="$network-sim"
docker network create --internal "$network" >/dev/null
cleanup() {
  docker rm -f "$sim" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null
}
trap cleanup EXIT
docker run -d --name "$sim" --network "$network" --network-alias sim game-tests:overcooked >/dev/null
if ! docker run --rm --network "$network" game-tests:overcooked-client; then
  docker logs "$sim"
  exit 1
fi
