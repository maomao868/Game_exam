# Overcooked-AI 开发实例

这一接入使用 Game Exam 的 standard 服务。开发实例使用原版 `asymmetric_advantages` 地图，固定 400 个联合时间步、种子 42。默认控制蓝色厨师（座位 0），绿色厨师由原版 `GreedyHumanModel` 控制。两个座位均支持。每次请求先根据同一时刻的状态计算队友动作，再由原版一次执行两名厨师的动作。游戏和只供模拟器使用的规划缓存均在 sim 中。原版源码版本与归档 SHA-256 见 [requirements.txt](requirements.txt)。

客户端使用 `GameClient.observe()` 获取原生厨房画面的 PNG，通过 `step(action, expected_step)` 提交 `north`、`south`、`east`、`west`、`stay` 或 `interact`。画面由原版 StateVisualizer 按每格 48 像素渲染，保留锅内烹饪计时。地图的订单为三洋葱汤。服务返回的步号、结束状态和墙钟时间遵循公共协议。

主指标 `native_return` 累计引擎返回的团队稀疏奖励，送餐数取自原生事件记录。达到原生 400 步时标记 `native_truncated`。公共协议的布尔字段 `episode_completed` 表示走完原生时长。种子、队友历史和 RNG、原始状态与评分日志留在可信端。

## 在仓库根目录验收

Linux Docker 环境可执行以下命令。第一组运行逐步原生对照、评分和公开 HTTP 客户端测试。第二组启动独立的 sim 和客户端容器，在内部网络上验证公开观测、动作重试和私有文件隔离。

```bash
docker build -f game_first_exam/tests/envs/overcooked.Dockerfile -t game-tests:overcooked .
docker run --rm --network none -v "$PWD:/repo:ro" game-tests:overcooked bash game_first_exam/tests/run.sh overcooked

docker build --target client -f game_first_exam/tests/envs/overcooked.Dockerfile -t game-tests:overcooked-client .
bash game_first_exam/tests/check-overcooked-network.sh
```

在安装了本目录依赖的 Python 3.10 环境里，也可直接执行 `python game_first_exam/tests/test_overcooked.py -v`。首次启动会在模拟器的原版包目录生成规划缓存，运行账户需要能写入其 `data/planners`。开发配置在 [overcooked-instance.json](../../tests/fixtures/overcooked-instance.json)。正式 exam 通过评审后单独加入任务套件。
