# TowerMind adapter

This development integration uses the upstream Unity Linux x86-64 player and both official TowerMind wrappers. `SOURCE.json` pins the archive and wrapper source by commit and SHA256. The simulator extracts a private copy and applies the level and seed selected for the run, following the upstream LLM example. All other settings come from the pinned archive.

Initialization resets through the TowerMind wrappers after the Gym bridge discovers its agent slots. The bridge uses the reported sensor names to route the player camera and JSON texture to the official observation wrapper. The first reset observation starts the public episode. The adapter records the first native terminal or interrupted transition and closes the episode.

The public `player-rgb-v1` profile exposes one cached 512×512 RGB player frame as PNG. Actions carry two coordinates in `[-3, 3]` and a native integer action type from 0 through 11 as a string, for example `"-1.5 1.2 2"`. The official wrapper handles native action mapping. The JSON state, raw step metadata, configuration, seed and fingerprints stay inside the simulator. The fingerprint covers the cached RGB pixels, JSON observation, instance identity and step outcomes.

The development instance reports cumulative native reward as its primary metric. It stores the native-invalid and total action counts from the JSON feedback, using the upstream example's criteria and excluding no-ops. The shared runtime's Boolean outcome records native termination with the base alive, using health directly from the native observation.

The Python ML-Agents gRPC listener binds to the simulator's own IPv4 loopback. The network test uses independent sim and client images, an internal Docker network and no shared mounts. Its client only carries the shared HTTP client, the connection helper and the probe. Keep those boundaries when packaging a Harbor task. Upstream static assets are public independently of access to the live simulator.

The files-only image carries implementation and dependency inputs. The test image downloads and verifies the original assets at build time. It uses the upstream Colab example's Xvfb screen settings and lets Unity select its graphics backend. The image includes Mesa's software OpenGL and Vulkan drivers. The simulator loads the Gym bridge from the installed ML-Agents distribution directly because the package's Gym registry initializer attempts a remote manifest fetch. The Linux regression runs the stock wrappers with the upstream LLM launch sequence first, then compares adapter rewards and termination on the same action sequence. Its development instance is for integration tests.

Run from the repository root on a Linux Docker host.

```bash
docker build -f game_first_exam/tests/envs/towermind.Dockerfile -t game-tests:towermind .
docker run --rm --network none -v "$PWD:/repo:ro" game-tests:towermind bash game_first_exam/tests/run.sh towermind
docker build --target client -f game_first_exam/tests/envs/towermind.Dockerfile -t game-tests:towermind-client .
bash game_first_exam/tests/check-towermind-network.sh
```
