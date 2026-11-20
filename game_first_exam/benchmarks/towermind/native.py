"""Pinned ML-Agents bridge. Only the simulator process can reach the Unity RPC listener."""
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import distribution
from importlib.util import module_from_spec, spec_from_file_location
from json import JSONDecodeError

import grpc
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.rpc_communicator import (
    RpcCommunicator,
    UnityToExternalServicerImplementation,
    add_UnityToExternalProtoServicer_to_server,
)
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel


RPC_PORT = 5005
NO_OP = (0.0, 0.0, 6)


def load_source(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_gym_bridge():
    # Importing mlagents_envs.envs fetches a remote registry at module import.
    # Load only the Gym bridge from the pinned, installed distribution.
    path = distribution("mlagents-envs").locate_file("mlagents_envs/envs/unity_gym_env.py")
    return load_source("_towermind_unity_gym", path).UnityToGymWrapper


class LoopbackCommunicator(RpcCommunicator):
    def create_server(self):
        # ML-Agents 1.1.0 otherwise binds [::]. The public HTTP server is a separate listener.
        self.check_port(self.port)
        self.server = grpc.server(
            ThreadPoolExecutor(max_workers=10), options=(("grpc.so_reuseport", 0),)
        )
        self.unity_to_external = UnityToExternalServicerImplementation()
        try:
            add_UnityToExternalProtoServicer_to_server(self.unity_to_external, self.server)
            if self.server.add_insecure_port(f"127.0.0.1:{self.port}") != self.port:
                raise RuntimeError("TowerMind RPC listener failed to bind loopback")
            self.server.start()
        except Exception:
            self.server.stop(0)
            self.unity_to_external.parent_conn.close()
            self.unity_to_external.child_conn.close()
            raise
        self.is_open = True


class LocalUnity(UnityEnvironment):
    _initializing = True

    @staticmethod
    def _get_communicator(worker_id, base_port, timeout_wait):
        return LoopbackCommunicator(worker_id, base_port, timeout_wait)

    def reset(self):
        if not self._initializing:
            raise RuntimeError("TowerMind simulator supports one episode")
        return super().reset()


def multimodal_observations(gym, wrappers):
    # The stock wrapper expects the camera followed by the text texture.
    # The Gym bridge returns visual sensors in the order announced by Unity.
    visual = [spec for spec in gym.group_spec.observation_specs if len(spec.shape) == 3]
    cameras = [
        index for index, spec in enumerate(visual)
        if spec.name == "CameraSensor" and spec.shape in ((512, 512, 3), (3, 512, 512))
    ]
    text_sensors = [index for index, spec in enumerate(visual) if spec.name == "RenderTextureSensor"]
    specs = [(spec.name, spec.shape) for spec in visual]
    if len(cameras) != 1 or len(text_sensors) != 1:
        raise ValueError(f"expected one native RGB camera and one text texture, got {specs}")
    camera, = cameras
    text, = text_sensors

    class NativeObservations(wrappers.TowerMindMultiModalObsWrapper):
        def _convert_obs(self, observation):
            try:
                return super()._convert_obs([observation[camera], observation[text]])
            except JSONDecodeError as error:
                raise ValueError(
                    f"TowerMind text texture is not valid JSON at offset {error.pos}, "
                    f"decoded length {len(error.doc)}, native sensors {specs}"
                ) from None

    return NativeObservations(gym, use_image=True, use_text=True, use_state=False)


def open_native(player, wrappers_path, seed):
    """Run the upstream startup sequence before exposing the first decision."""
    gym_wrapper = load_gym_bridge()
    wrappers = load_source("_towermind_upstream_wrappers", wrappers_path)
    channel = EngineConfigurationChannel()
    channel.set_configuration_parameters(target_frame_rate=-1, time_scale=20.0, capture_frame_rate=60)
    unity = LocalUnity(
        file_name=str(player), seed=seed, base_port=RPC_PORT, timeout_wait=60,
        side_channels=[channel], log_folder=str(player.parent),
    )
    try:
        gym = gym_wrapper(unity, uint8_visual=True, allow_multiple_obs=True)
        env = wrappers.TowerMindActionMappingWrapper(multimodal_observations(gym, wrappers))
        # UnityToGymWrapper resets during its constructor to inspect agent slots.
        # TowerMind's example then resets the wrapped environment to obtain the
        # playable observation.
        initial = env.reset()
        unity._initializing = False
        decision, terminal = unity.get_steps(gym.name)
        if len(decision) != 1 or len(terminal):
            raise ValueError("unexpected TowerMind initial decision")
        return env, initial
    except Exception:
        unity.close()
        raise
