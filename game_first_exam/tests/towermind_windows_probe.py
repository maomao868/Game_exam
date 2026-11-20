"""Test the official Windows player under Wine on the Linux CI runner."""
import json
import os
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import towermind_fixture
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel
from native import LocalUnity, NO_OP, load_gym_bridge, load_source


def main():
    assets = Path("/opt/towermind")
    wrappers = load_source("_towermind_windows_wrappers", assets / "wrappers.py")
    with TemporaryDirectory() as directory, ZipFile(assets / "windows.zip") as package:
        work = Path(directory)
        package.extractall(work)
        player = work / "windows/TowerDefence.exe"
        config = player.parent / "TowerDefence_Data/StreamingAssets/Config"
        path = config / "EnvConfig.json"
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
        settings["RandomSeed"] = 42
        path.write_text(json.dumps(settings), encoding="utf-8")
        (config / "FixedLevelsConfig.json").write_text('{"CurrentLevel":0}', encoding="utf-8")
        os.environ["WINEPREFIX"] = str(work / "prefix")
        os.environ["WINEDLLOVERRIDES"] = "mscoree,mshtml="
        os.environ["WINEDEBUG"] = "-all"
        launcher = work / "launch.x86_64"
        launcher.write_text(f'#!/bin/sh\nexec /usr/lib/wine/wine64 {shlex.quote(str(player))} "$@"\n')
        launcher.chmod(0o700)
        channel = EngineConfigurationChannel()
        channel.set_configuration_parameters(target_frame_rate=-1, time_scale=20.0, capture_frame_rate=60)
        log = work / "player.log"
        unity = None
        try:
            unity = LocalUnity(
                file_name=str(launcher), timeout_wait=90, side_channels=[channel],
                additional_args=["-batchmode", "-force-d3d11", "-logFile", f"Z:{log}"],
            )
            bridge = load_gym_bridge()(unity, uint8_visual=True, allow_multiple_obs=True)
            observations = wrappers.TowerMindMultiModalObsWrapper(
                bridge, use_image=True, use_text=True, use_state=False
            )
            game = wrappers.TowerMindActionMappingWrapper(observations)
            observation = game.reset()
            assert set(observation) == {"image", "text"}
            for action in [NO_OP, (-1.5, 1.2, 2)] * 3:
                observation, _, done, _ = game.step(action)
                assert not done and "Agent_Last_Action_Info" in observation["text"]
            print("Official TowerMind Windows player and JSON decoder ran six decisions under Wine.")
        except json.JSONDecodeError as error:
            raise ValueError(f"Windows player text decode failed at offset {error.pos}, length {len(error.doc)}") from None
        finally:
            if unity is not None and unity._loaded:
                unity.close()
            if log.is_file():
                for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().startswith(("Renderer:", "Direct3D:", "Forcing GfxDevice:")):
                        print(line.strip())


if __name__ == "__main__":
    main()
