"""Verify the public projection, action validation and grading without launching Unity."""
import base64
from contextlib import contextmanager
from io import BytesIO
from json import JSONDecodeError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from towermind_fixture import instance
import adapter
from config_schema import validate_instance
from grade import grade
from metric_rules import validate_metrics
from native_assets import ARCHIVE_SHA256
from server import EnvironmentFault, Game, InvalidAction


def native_observation(shade=91, health=20, action_type=6, error_code=0):
    return {
        "image": np.full((512, 512, 3), shade, dtype=np.uint8),
        "text": {
            "Level_Current_Health": health,
            "Agent_Last_Action_Info": {"Action_Index": action_type, "Error_Code": error_code},
            "private": "hidden-wave-sentinel",
        },
    }


class StubNative:
    def __init__(self, outcome):
        self.outcome = outcome
        self.actions = []
        self.closed = False

    def step(self, action):
        self.actions.append(action)
        health = 0 if self.outcome == "destroyed" else 20
        reward = {"destroyed": -20.0, "feedback": -1.01, "nonfinite_reward": float("nan")}.get(self.outcome, 0.0)
        observation = native_observation(92, health, action[2], int(self.outcome == "feedback"))
        return observation, np.float32(reward), True, {
            "step": SimpleNamespace(interrupted=[self.outcome == "interrupted"])
        }

    def close(self):
        self.closed = True


@contextmanager
def session(outcome):
    config = instance()
    native = StubNative(outcome)
    with TemporaryDirectory() as output:
        with (
            patch.object(adapter, "version", side_effect=config["engine_versions"].__getitem__),
            patch.object(adapter, "prepare_game", return_value=Path("unused")),
            patch.object(adapter, "open_native", return_value=(native, native_observation())),
        ):
            game_adapter = adapter.Adapter(config)
        config["initial_state_sha256"] = game_adapter.fingerprint()
        with patch("server.Recorder.frame"):  # PNG projection is covered below; no encoder needed here.
            game = Game(game_adapter, config, output)
            try:
                yield game, config, native
            finally:
                game.close()


class TowerMindContract(unittest.TestCase):
    def test_gym_bridge_can_load_offline(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected runtime download")):
            from native import load_gym_bridge

            self.assertEqual(load_gym_bridge().__name__, "UnityToGymWrapper")

    def test_explicit_reset_routes_image_and_text_to_the_official_wrapper(self):
        import native

        unity = native.LocalUnity.__new__(native.LocalUnity)
        player_frame = native_observation()["image"]
        payloads = iter((None, ["text texture", player_frame, "private vector"]))
        unity.get_steps = lambda _: ([object()], [])

        def receive_reset(player):
            player.payload = next(payloads)

        class GymBridge:
            name = "tower-defender"
            group_spec = SimpleNamespace(observation_specs=[
                SimpleNamespace(name="VectorSensor", shape=(32,)),
                SimpleNamespace(name="RenderTextureSensor", shape=(128, 128, 3)),
                SimpleNamespace(name="CameraSensor", shape=player_frame.shape),
            ])

            def __init__(self, player, **_):
                self.player = player
                player.reset()

            def reset(self):
                self.player.reset()
                return self.player.payload

        class Modalities:
            def __init__(self, gym, **flags):
                self.gym = gym
                self.flags = flags

            def _convert_obs(self, observation):
                return {"image": observation[0], "text": observation[1]}

            def reset(self):
                return self._convert_obs(self.gym.reset())

        wrappers = SimpleNamespace(
            TowerMindMultiModalObsWrapper=Modalities,
            TowerMindActionMappingWrapper=lambda env: env,
        )
        with (
            patch.object(native, "LocalUnity", return_value=unity),
            patch.object(native, "load_gym_bridge", return_value=GymBridge),
            patch.object(native, "load_source", return_value=wrappers),
            patch.object(native.UnityEnvironment, "reset", autospec=True, side_effect=receive_reset) as reset,
        ):
            env, initial = native.open_native(Path("td.x86_64"), Path("wrappers.py"), 42)
            self.assertEqual(env.flags, {"use_image": True, "use_text": True, "use_state": False})
            self.assertEqual(set(initial), {"image", "text"})
            self.assertIs(initial["image"], player_frame)
            self.assertEqual(initial["text"], "text texture")
            with self.assertRaisesRegex(RuntimeError, "one episode"):
                env.reset()
            self.assertEqual(reset.call_count, 2)

    def test_missing_or_ambiguous_native_sensor_fails_closed(self):
        from native import multimodal_observations

        other = SimpleNamespace(name="RenderTextureSensor", shape=(512, 512, 3))
        camera = SimpleNamespace(name="CameraSensor", shape=(512, 512, 3))
        for specs in ([other], [camera], [camera, camera, other], [camera, other, other]):
            gym = SimpleNamespace(group_spec=SimpleNamespace(observation_specs=specs))
            with self.subTest(specs=specs), self.assertRaisesRegex(ValueError, "expected one"):
                multimodal_observations(gym, None)

    def test_text_decode_diagnostic_omits_private_data(self):
        from native import multimodal_observations

        class Modalities:
            def __init__(self, _, **flags):
                pass

            def _convert_obs(self, observation):
                raise JSONDecodeError("invalid", "hidden-wave-sentinel", 0)

        specs = [
            SimpleNamespace(name="CameraSensor", shape=(3, 512, 512)),
            SimpleNamespace(name="RenderTextureSensor", shape=(3, 128, 128)),
        ]
        gym = SimpleNamespace(group_spec=SimpleNamespace(observation_specs=specs))
        env = multimodal_observations(gym, SimpleNamespace(TowerMindMultiModalObsWrapper=Modalities))
        with self.assertRaisesRegex(ValueError, "offset 0, decoded length 20") as error:
            env._convert_obs([None, None])
        self.assertNotIn("hidden-wave-sentinel", str(error.exception))

    def test_schema_rejects_drift(self):
        config = instance()
        self.assertEqual(config["engine_archive_sha256"], ARCHIVE_SHA256)
        validate_instance(config)
        for update in ({"seed": 0}, {"level_id": 9}, {"engine_archive_sha256": "1" * 64},
                       {"observation_profile": "unfiltered-json"}, {"hidden_field": True}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_instance(dict(config, **update))

    def test_rgb_is_only_public_observation_and_reading_is_pure(self):
        with session("completed") as (game, config, native):
            before = game.adapter.fingerprint()
            self.assertEqual(game.spec()["reset_budget"], 0)
            observation = game.observe()["observation"]
            self.assertEqual(set(observation), {"image_png_base64"})
            with Image.open(BytesIO(base64.b64decode(observation["image_png_base64"]))) as image:
                self.assertEqual((image.mode, image.size, image.getpixel((0, 0))), ("RGB", (512, 512), (91, 91, 91)))
            self.assertEqual(game.observe()["observation"], observation)
            self.assertEqual(game.adapter.fingerprint(), before)
            self.assertEqual(native.actions, [])
            self.assertNotIn("hidden-wave-sentinel", str(game.spec()))
            self.assertNotIn(config["engine_archive_sha256"], str(game.spec()))
        self.assertTrue(native.closed)

    def test_server_rejects_malformed_action_before_game_moves(self):
        with session("completed") as (game, _, native):
            for action in ("reset", "3.01 0 1", "0 0 12", "nan 0 0", "0 0 0\n", "0  0 1", [0, 0, 0]):
                with self.subTest(action=action), self.assertRaises(InvalidAction):
                    game.submit({"action": action, "expected_step": 0, "request_id": "bad"})
            self.assertEqual((game.steps, native.actions), (0, []))

    def test_native_outcomes_and_public_early_stop_are_distinct(self):
        for outcome, reason, success, score in (
            ("completed", "native_terminated", True, 0.0),
            ("destroyed", "native_terminated", False, -20.0),
            ("interrupted", "native_truncated", False, 0.0),
            ("early", "agent_finished", False, 0.0),
        ):
            with self.subTest(outcome=outcome), session(outcome) as (game, config, native):
                if outcome == "early":
                    game.finalize("agent_finished")
                else:
                    action = {"action": "-3.000000000 3.000000000 11", "expected_step": 0, "request_id": "legal"}
                    self.assertTrue(game.submit(action)["done"])
                    self.assertTrue(game.submit(action)["done"])  # duplicate must not execute again
                    self.assertEqual(native.actions, [(-3.0, 3.0, 11)])
                result = grade(game.final, config, validate_metrics)
                self.assertEqual((result["reason"], result["primary_score"]), (reason, score))
                self.assertEqual(game.final["success"], success)

    def test_native_reward_and_reported_action_outcome_are_independent(self):
        with session("feedback") as (game, config, _):
            game.submit({"action": "0 0 2", "expected_step": 0, "request_id": "mixed"})
            self.assertEqual(grade(game.final, config, validate_metrics)["primary_score"], float(np.float32(-1.01)))
            self.assertEqual(game.final["metrics"]["base_health"], 20)
            self.assertEqual(game.final["metrics"]["native_counted_actions"], 1)
            self.assertEqual(game.final["metrics"]["native_invalid_actions"], 1)
            game.final["metrics"]["native_invalid_actions"] = 2
            with self.assertRaisesRegex(ValueError, "action counts"):
                validate_metrics(game.final, config)

    def test_no_op_is_excluded_from_native_action_counts(self):
        with session("completed") as (game, _, _):
            game.submit({"action": "0 0 6", "expected_step": 0, "request_id": "no-op"})
            self.assertEqual(game.final["metrics"]["native_counted_actions"], 0)
            self.assertEqual(game.final["metrics"]["native_invalid_actions"], 0)

    def test_nonfinite_native_reward_invalidates_attempt(self):
        with session("nonfinite_reward") as (game, _, _):
            with self.assertRaises(EnvironmentFault):
                game.submit({"action": "0 0 6", "expected_step": 0, "request_id": "reward-drift"})
            self.assertEqual(game.final["reason"], "environment_error")
            self.assertFalse(game.final["result_valid"])


if __name__ == "__main__":
    unittest.main()
