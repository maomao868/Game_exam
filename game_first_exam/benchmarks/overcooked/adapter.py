"""Run one upstream cooperative kitchen episode per simulator process."""
from importlib.metadata import version

import numpy as np
import pygame
from overcooked_ai_py.agents.agent import GreedyHumanModel
from overcooked_ai_py.mdp.actions import Action, Direction
from overcooked_ai_py.mdp.overcooked_env import OvercookedEnv
from overcooked_ai_py.mdp.overcooked_mdp import OvercookedGridworld
from overcooked_ai_py.visualization.state_visualizer import StateVisualizer

from config_schema import validate_instance
from contracts import Transition
from encoding import png, state_hash
from instance_schema import CAPABILITIES

ACTIONS = {
    "north": Direction.NORTH, "south": Direction.SOUTH, "east": Direction.EAST,
    "west": Direction.WEST, "stay": Action.STAY, "interact": Action.INTERACT,
}


class Adapter:
    def __init__(self, instance, assets=None):
        validate_instance(instance)
        for package, expected in instance["engine_versions"].items():
            if version(package) != expected:
                raise ValueError(f"unexpected {package} version")
        self.player_index = instance["player_index"]
        self._partner_rng = np.random.RandomState(instance["seed"]).get_state()
        mdp = OvercookedGridworld.from_layout_name(instance["env_id"])
        self.env = OvercookedEnv.from_mdp(mdp, horizon=instance["horizon"], info_level=0)
        self.partner = GreedyHumanModel(self.env.mlam)
        self.partner.set_agent_index(1 - self.player_index)
        self.partner.set_mdp(mdp)
        self.visualizer = StateVisualizer(tile_size=48, is_rendering_hud=False)
        self._render()
        self._closed = False

    def _render(self):
        surface = self.visualizer.render_state(self.env.state, self.env.mdp.terrain_mtx)
        self._frame = np.ascontiguousarray(pygame.surfarray.array3d(surface).transpose(1, 0, 2))
        self._frame.flags.writeable = False
        self._png = png(self._frame)

    def spec(self):
        return {
            "adapter_version": "1.0.0", "capabilities": dict(CAPABILITIES),
            "action_schema": {"type": "string", "enum": list(ACTIONS)},
            "player_index": self.player_index,
            "player_color": ("blue", "green")[self.player_index],
            "observation": "Native kitchen image. Orders are three-onion soup. One submission advances both chefs.",
        }

    def observe(self):
        return {"image_png_base64": self._png}

    def frame(self):
        return self._frame

    def step(self, action):
        if self._closed or self.env.is_done():
            raise ValueError("episode closed")
        if action not in ACTIONS:
            raise ValueError("unknown kitchen action")
        # The native partner uses NumPy's legacy global RNG to resolve ties.
        # Scope that stream to this episode in the synchronous sim.
        previous_rng = np.random.get_state()
        np.random.set_state(self._partner_rng)
        try:
            other, _ = self.partner.action(self.env.state)
            own = ACTIONS[action]
            joint = (own, other) if self.player_index == 0 else (other, own)
            state, reward, done, _ = self.env.step(joint)
        finally:
            self._partner_rng = np.random.get_state()
            np.random.set_state(previous_rng)
        terminated = bool(self.env.mdp.is_terminal(state))
        self._render()
        return Transition(float(reward), terminated, bool(done and not terminated))

    def success(self):
        return bool(self.env.is_done())

    def metrics(self):
        stats = self.env.game_stats
        return {
            "native_return": float(sum(stats["cumulative_sparse_rewards_by_agent"])),
            "deliveries": sum(map(len, stats["soup_delivery"])),
            "native_steps": self.env.state.timestep,
        }

    def fingerprint(self):
        previous = self.partner.prev_state
        return state_hash({
            "layout": self.env.mdp.layout_name, "player_index": self.player_index,
            "state": self.env.state.to_dict(), "stats": self.metrics(),
            "partner_last_state": None if previous is None else previous.to_dict(),
            "partner_rng": self._partner_rng,
        })

    def close(self):
        self._closed = True
