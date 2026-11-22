"""Exercise the development fixture through the real service and independent upstream engine."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import numpy as np
import pygame
from overcooked_ai_py.agents.agent import GreedyHumanModel
from overcooked_ai_py.mdp.actions import Action, Direction
from overcooked_ai_py.mdp.overcooked_env import OvercookedEnv
from overcooked_ai_py.mdp.overcooked_mdp import OvercookedGridworld
from overcooked_ai_py.visualization.state_visualizer import StateVisualizer

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "game_first_exam/runtime"), str(ROOT / "game_first_exam/benchmarks/overcooked"),
                str(ROOT / "shared/connection")]
import instance_schema
from adapter import Adapter
from config_schema import register_instance_schema
from grade import grade
from metric_rules import validate_metrics
from server import Game, InvalidAction

register_instance_schema(instance_schema)
FIXTURE = Path(__file__).parent / "fixtures/overcooked-instance.json"
COMMAND = {Direction.NORTH: "north", Direction.SOUTH: "south", Direction.EAST: "east",
           Direction.WEST: "west", Action.STAY: "stay", Action.INTERACT: "interact"}


class KitchenTests(unittest.TestCase):
    def test_full_native_episode(self):
        config = json.loads(FIXTURE.read_text())
        mdp = OvercookedGridworld.from_layout_name("asymmetric_advantages")
        native = OvercookedEnv.from_mdp(mdp, horizon=400, info_level=0)
        # Deterministic driver for the tested chef. The teammate uses upstream defaults.
        chefs = [GreedyHumanModel(native.mlam, auto_unstuck=False), GreedyHumanModel(native.mlam)]
        for index, chef in enumerate(chefs):
            chef.set_agent_index(index)
            chef.set_mdp(mdp)
        visualizer = StateVisualizer(tile_size=48, is_rendering_hud=False)
        np.random.seed(config["seed"])
        with tempfile.TemporaryDirectory() as directory:
            game = Game.open(Adapter, config, None, directory)
            try:
                self.assertIsNone(game.final, game.final)
                initial = game.adapter.fingerprint()
                for _ in range(2):
                    game.observe()
                    game.adapter.observe()
                    game.adapter.frame()
                    game.adapter.metrics()
                with self.assertRaises(InvalidAction):
                    game.submit({"action": "reset", "expected_step": 0, "request_id": "invalid"})
                self.assertEqual(initial, game.adapter.fingerprint())
                for index in range(400):
                    before = native.state
                    joint = tuple(chef.action(before)[0] for chef in chefs)
                    state, reward, done, info = native.step(joint)
                    body = {"action": COMMAND[joint[0]], "expected_step": index, "request_id": str(index)}
                    previous_return = game.reward
                    response = game.submit(body)
                    self.assertEqual(response["step"], index + 1)
                    self.assertEqual(response["done"], done)
                    self.assertEqual(game.reward - previous_return, reward)
                    self.assertEqual(game.adapter.env.state.to_dict(), state.to_dict())
                    surface = visualizer.render_state(state, mdp.terrain_mtx)
                    np.testing.assert_array_equal(game.adapter.frame(), pygame.surfarray.array3d(surface).swapaxes(0, 1))
                    if index == 0:
                        self.assertEqual(response, game.submit(body))
                result = grade(game.final, config, validate_metrics)
                self.assertEqual(game.final["reason"], "native_truncated")
                self.assertEqual(result["primary_score"], info["episode"]["ep_sparse_r"])
                deliveries = sum(map(len, info["episode"]["ep_game_stats"]["soup_delivery"]))
                self.assertGreater(deliveries, 0)
                self.assertEqual(result["native_metrics"]["deliveries"], deliveries)
                self.assertGreater(result["primary_score"], 0)
                print(f"Matched 400 native steps, {deliveries} deliveries, return {game.reward:g}")
                with self.assertRaises(ValueError):
                    game.submit({"action": "stay", "expected_step": 400, "request_id": "extra"})
            finally:
                game.close()
            self.assertIsNone(json.loads((Path(directory) / "recording.json").read_text())["render_error"])

    def test_public_client(self):
        from http.server import HTTPServer
        from threading import Thread
        from game_client import GameClient
        from server import Handler

        config = json.loads(FIXTURE.read_text())
        with tempfile.TemporaryDirectory() as directory, HTTPServer(("127.0.0.1", 0), Handler) as http:
            game = Game.open(Adapter, config, None, directory)
            http.game = game
            thread = Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                client = GameClient(url=f"http://127.0.0.1:{http.server_port}")
                self.assertEqual(client.spec()["reset_budget"], 0)
                self.assertEqual(client.observe()["step"], 0)
                response = client.step("interact", expected_step=0)
                self.assertEqual(response["step"], 1)
                self.assertEqual(set(response["observation"]), {"image_png_base64"})
            finally:
                http.shutdown()
                thread.join()
                game.close()

    def test_second_seat(self):
        config = {**json.loads(FIXTURE.read_text()), "player_index": 1}
        adapter = Adapter(config)
        try:
            native = OvercookedEnv.from_mdp(OvercookedGridworld.from_layout_name(config["env_id"]),
                                            horizon=config["horizon"], info_level=0)
            teammate = GreedyHumanModel(native.mlam)
            teammate.set_agent_index(0)
            teammate.set_mdp(native.mdp)
            np.random.seed(config["seed"])
            commands = {name: move for move, name in COMMAND.items()}
            for action in ("west", "interact", "north", "stay"):
                ai, _ = teammate.action(native.state)
                state, reward, _, _ = native.step((ai, commands[action]))
                self.assertEqual(adapter.step(action).reward, reward)
                self.assertEqual(adapter.env.state.to_dict(), state.to_dict())
        finally:
            adapter.close()


if __name__ == "__main__":
    unittest.main()
