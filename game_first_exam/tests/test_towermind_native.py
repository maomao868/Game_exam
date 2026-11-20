"""Native equivalence and timing checks for the pinned TowerMind Linux player."""
import json
import socket
from json import JSONDecodeError
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

import numpy as np
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel

from towermind_fixture import instance
from adapter import Adapter, NATIVE_ASSETS
from native import NO_OP, RPC_PORT, load_gym_bridge, load_source
from native_assets import prepare_game
from metric_rules import validate_metrics
from server import Game


COMMANDS = [("0 0 6", NO_OP), ("-1.5 1.2 2", (-1.5, 1.2, 2))] * 6
MAX_REFERENCE_DECISIONS = 4096


def report_texture_transport(player, wrappers):
    # The native recorder writes the same payload before it goes through the
    # texture transport. Enable it only in this disposable diagnostic copy.
    config_path = player.parent / "td_Data/StreamingAssets/Config/EnvConfig.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    records = player.parent / "diagnostic-records"
    records.mkdir()
    config.update(IsRecordingEnabled=1, RecordingPath=str(records))
    config_path.write_text(json.dumps(config), encoding="utf-8")
    for args in ([], ["-force-gfx-direct"]):
        label = args[0] if args else "default"
        log_path = player.parent / f"diagnostic-{label}.log"
        settings = EngineConfigurationChannel()
        settings.set_configuration_parameters(target_frame_rate=-1, time_scale=20.0, capture_frame_rate=60)
        try:
            unity = UnityEnvironment(file_name=str(player), side_channels=[settings], timeout_wait=20,
                                     additional_args=args + ["-logFile", str(log_path)], seed=42)
            try:
                bridge = load_gym_bridge()(unity, uint8_visual=True, allow_multiple_obs=True)
                texture = bridge.reset()[1]
                red = texture[0]
                rows = np.count_nonzero(red, axis=1)
                print(f"reference {label} nonzero texture pixels in first/last 20 rows: {rows[:20]}, {rows[-20:]}")
                try:
                    wrappers.get_json_from_obs(texture)
                except json.JSONDecodeError as error:
                    print(f"reference {label} stock decoder: length {len(error.doc)}, offset {error.pos}")
                else:
                    print(f"reference {label} stock decoder: valid JSON")
                paths = sorted(records.glob("*/game_internal_states/*"), key=lambda p: p.stat().st_mtime_ns)
                if not paths:
                    print(f"reference {label} native diagnostic record absent")
                    continue
                recorded = paths[-1].read_text(encoding="utf-8-sig")
                try:
                    json.loads(recorded)
                except json.JSONDecodeError as error:
                    print(f"reference {label} recorder: length {len(recorded)}, invalid JSON at {error.pos}")
                else:
                    print(f"reference {label} recorder: length {len(recorded)}, valid JSON")
                expected = np.array([ord(char) % 256 for char in recorded] + [64], dtype=np.uint8)
                header = expected[:12].tobytes()
                values = np.arange(256) / 255.0
                linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
                srgb = np.where(values <= 0.0031308, 12.92 * values, 1.055 * values ** (1 / 2.4) - 0.055)
                for transfer, lut in (("identity", values), ("linear", linear), ("srgb", srgb)):
                    decoded = np.round(lut * 255).astype(np.uint8)[red]
                    actual = decoded[decoded != 0]
                    common = np.minimum(np.bincount(expected, minlength=256), np.bincount(actual, minlength=256)).sum()
                    print(f"reference {label} {transfer} byte overlap: {common}/{len(expected)}")
                    for rotation in range(4):
                        oriented = np.rot90(decoded, rotation)
                        for mirrored, plane in enumerate((oriented, oriented[:, ::-1])):
                            stream = plane.ravel().tobytes()
                            circular = stream + stream
                            start = circular.find(header)
                            end = circular.find(b"@", start) if start >= 0 else -1
                            if 0 <= start < len(stream) and 0 <= end - start < len(stream):
                                try:
                                    state = json.loads(circular[start:end])
                                except (ValueError, UnicodeDecodeError):
                                    continue
                                if isinstance(state, dict) and "Level_Current_Health" in state:
                                    print(f"reference {label} valid JSON with {transfer}, "
                                          f"rotation={rotation * 90}, mirrored={bool(mirrored)}, offset={start}")
            finally:
                unity.close()
        except Exception as error:
            print(f"reference {label} transport probe failed: {type(error).__name__}")
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith(("Renderer:", "Vendor:", "Version:", "GfxDevice:", "OpenGL", "Vulkan")):
                    print(f"reference {label}: {line.strip()}")


class TowerMindNative(unittest.TestCase):
    def test_01_upstream_reference_matches_the_adapter_through_termination(self):
        config = instance()
        with TemporaryDirectory() as workspace:
            player = prepare_game(NATIVE_ASSETS, Path(workspace), config)
            # Run the official LLM example's Gym sequence without a model.
            # This reference uses plain UnityEnvironment and both stock wrappers.
            wrappers = load_source("_towermind_reference_wrappers", NATIVE_ASSETS / "wrappers.py")
            settings = EngineConfigurationChannel()
            settings.set_configuration_parameters(target_frame_rate=-1, time_scale=20.0, capture_frame_rate=60)
            unity = UnityEnvironment(file_name=str(player), side_channels=[settings],
                                     timeout_wait=60, log_folder=str(player.parent))
            try:
                bridge = load_gym_bridge()(unity, uint8_visual=True, allow_multiple_obs=True)
                observations = wrappers.TowerMindMultiModalObsWrapper(
                    bridge, use_image=True, use_text=True, use_state=False
                )
                env = wrappers.TowerMindActionMappingWrapper(observations)
                try:
                    initial = env.reset()
                except JSONDecodeError as error:
                    specs = [(spec.name, spec.shape) for spec in bridge.group_spec.observation_specs]
                    unity.close()
                    report_texture_transport(player, wrappers)
                    self.fail(
                        f"stock TowerMind LLM wrappers failed during reset before Game Exam: "
                        f"JSON offset {error.pos}, decoded length {len(error.doc)}, sensors {specs}"
                    )
                self.assertEqual(set(initial), {"image", "text"})
                expected = []
                for index in range(MAX_REFERENCE_DECISIONS):
                    command, action = COMMANDS[index] if index < len(COMMANDS) else ("0 0 6", NO_OP)
                    observation, reward, done, info = env.step(action)
                    interrupted = info["step"].interrupted[0] if done else False
                    status = observation["text"]
                    expected.append((command, float(reward), bool(done), bool(interrupted),
                                     status["Level_Current_Health"], status["Agent_Last_Action_Info"]))
                    if done:
                        break
                self.assertTrue(done, "expected a native ending within the reference decision cap")
            finally:
                if unity._loaded:
                    unity.close()

        adapter = Adapter(config)
        try:
            with socket.create_connection(("127.0.0.1", RPC_PORT), timeout=2):
                pass
            initial_frame = initial["image"]
            if initial_frame.shape == (3, 512, 512):
                initial_frame = initial_frame.transpose(1, 2, 0)
            self.assertEqual(adapter.frame().shape, initial_frame.shape)
            self.assertEqual(adapter.frame().dtype, np.uint8)
            self.assertGreater(np.ptp(adapter.frame()), 0, "expected a rendered player camera")
            reference_return = 0.0
            counted = invalid = 0
            for index, (command, reward, done, interrupted, health, outcome) in enumerate(expected):
                if index in (0, 1, 5):
                    before = adapter.fingerprint()
                    adapter.spec()
                    adapter.observe()
                    adapter.frame()
                    time.sleep(1)
                    adapter.observe()
                    self.assertEqual(adapter.fingerprint(), before)
                transition = adapter.step(command)
                self.assertEqual(
                    (transition.reward, transition.terminated, transition.truncated),
                    (reward, done and not interrupted, interrupted),
                    f"decision {index + 1}",
                )
                reference_return += reward
                if outcome["Action_Index"] != 6:
                    counted += 1
                    invalid += int(outcome["Error_Code"] > 0)
            metrics = adapter.metrics()
            self.assertEqual(metrics["native_return"], reference_return)
            self.assertEqual(metrics["base_health"], health)
            self.assertEqual(metrics["native_counted_actions"], counted)
            self.assertEqual(metrics["native_invalid_actions"], invalid)
            with self.assertRaisesRegex(ValueError, "episode closed"):
                adapter.step("0 0 6")
        finally:
            adapter.close()

    def test_public_service_keeps_native_result_on_a_budget_stop(self):
        config = instance()
        config["max_steps"] = 1
        adapter = Adapter(config)
        config["initial_state_sha256"] = adapter.fingerprint()
        with TemporaryDirectory() as directory:
            game = Game(adapter, config, directory)
            try:
                reply = game.submit({"action": "0 0 0", "expected_step": 0, "request_id": "native-first"})
                self.assertTrue(reply["done"])
                self.assertEqual(set(reply["observation"]), {"image_png_base64"})
                self.assertEqual(game.final["reason"], "step_limit")
                self.assertFalse(game.final["success"])
                validate_metrics(game.final, config)
                self.assertIsNone(game.recorder.error)
            finally:
                game.close()


if __name__ == "__main__":
    unittest.main()
