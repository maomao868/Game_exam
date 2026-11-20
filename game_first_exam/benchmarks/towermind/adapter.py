"""Expose one cached player RGB frame and one native decision per accepted action."""
from hashlib import sha256
from importlib.metadata import version
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import numpy as np

from config_schema import validate_instance
from contracts import Transition
from encoding import png, state_hash
from instance_schema import CAPABILITIES
from native_assets import prepare_game


NATIVE_ASSETS = Path("/opt/towermind")
COORDINATE = r"-?(?:[0-2](?:\.[0-9]{1,9})?|3(?:\.0{1,9})?)"
ACTION_PATTERN = rf"{COORDINATE} {COORDINATE} (?:[0-9]|1[01])"
ACTION_LENGTH = 28


def parse_action(action):
    if not isinstance(action, str) or not re.fullmatch(ACTION_PATTERN, action):
        raise ValueError("expected 'x y action_type' within the declared bounds")
    x, y, action_type = action.split(" ")
    return float(x), float(y), int(action_type)


def open_native(player, wrappers_path, seed):
    from native import open_native as launch

    return launch(player, wrappers_path, seed)


class Adapter:
    def __init__(self, instance, assets=None):
        validate_instance(instance)
        for package, expected in instance["engine_versions"].items():
            if version(package) != expected:
                raise ValueError(f"TowerMind dependency version mismatch: {package}")
        self.instance = dict(instance)
        self._workspace = TemporaryDirectory(prefix="towermind-")
        self._env = None
        self._decisions = 0
        self._return = 0.0
        self._counted_actions = self._invalid_actions = 0
        self._terminated = self._truncated = False
        source = NATIVE_ASSETS if assets is None or not (assets / "linux.zip").is_file() else assets
        try:
            player = prepare_game(source, Path(self._workspace.name), instance)
            self._env, observation = open_native(player, source / "wrappers.py", instance["seed"])
            self._cache(observation)
        except Exception:
            self.close()
            raise

    def _cache(self, observation):
        health = observation["text"]["Level_Current_Health"]
        if type(health) is not int or health < 0:
            raise ValueError("invalid native TowerMind base health")
        image = observation["image"]
        if image.shape == (3, 512, 512):
            image = np.moveaxis(image, 0, -1)
        if image.shape != (512, 512, 3) or image.dtype != np.uint8:
            raise ValueError("expected native 512x512 RGB uint8 frame")
        self._image = np.array(image, copy=True, order="C")
        self._image.flags.writeable = False
        self._frame_sha256 = sha256(self._image).hexdigest()
        self._public_png = png(self._image)
        self._native_text = observation["text"]

    def spec(self):
        return {
            "adapter_version": "1.0.0",
            "capabilities": dict(CAPABILITIES),
            "action_schema": {"type": "string", "pattern": ACTION_PATTERN, "max_length": ACTION_LENGTH},
            "observation": "Cached native 512x512 RGB player frame encoded as PNG.",
            "actions": "Submit x y action_type. Coordinates are in [-3, 3], and action_type is 0–11.",
        }

    def observe(self):
        return {"image_png_base64": self._public_png}

    def step(self, action):
        if self._terminated or self._truncated:
            raise ValueError("episode closed")
        observation, reward, done, info = self._env.step(parse_action(action))
        reward = float(reward)
        if not math.isfinite(reward):
            raise ValueError("invalid native TowerMind reward")
        outcome = observation["text"]["Agent_Last_Action_Info"]
        action_type, error_code = outcome["Action_Index"], outcome["Error_Code"]
        if type(action_type) is not int or not 0 <= action_type <= 11 or type(error_code) is not int:
            raise ValueError("invalid native TowerMind action feedback")
        self._cache(observation)
        # Match the upstream LLM example's counters for reported actions.
        if action_type != 6:
            self._counted_actions += 1
            self._invalid_actions += int(error_code > 0)
        interrupted = bool(info["step"].interrupted[0]) if done else False
        self._terminated = bool(done and not interrupted)
        self._truncated = interrupted
        self._decisions += 1
        self._return += reward
        return Transition(reward, self._terminated, self._truncated)

    def success(self):
        # Compatibility flag for the shared service's native outcome record.
        return self._terminated and self._native_text["Level_Current_Health"] > 0

    def metrics(self):
        return {
            "native_return": self._return,
            "base_health": self._native_text["Level_Current_Health"],
            "native_decisions": self._decisions,
            "native_counted_actions": self._counted_actions,
            "native_invalid_actions": self._invalid_actions,
        }

    def fingerprint(self):
        # Unity does not export a complete engine checkpoint or the internal RNG state.
        return state_hash({
            "archive": self.instance["engine_archive_sha256"],
            "level": self.instance["level_id"], "seed": self.instance["seed"],
            "frame_sha256": self._frame_sha256, "decisions": self._decisions, "return": self._return,
            "text": self._native_text,
            "terminated": self._terminated, "truncated": self._truncated,
        })

    def frame(self):
        return self._image

    def close(self):
        try:
            if self._env is not None:
                env, self._env = self._env, None
                env.close()
        finally:
            self._workspace.cleanup()
