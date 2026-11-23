# Collab-Overcooked

这是 Game Exam 的原生双角色套件，入口为 `harbor run --game-suite collab-overcooked`。论文将同一模型放在 Chef（Bob）和 Assistant（Alice）两个位置。双方共享厨房状态，各有可执行动作，只有 Chef 收到完整食谱。两者通过作者定义的语言对话和 `request(...)` 协作。[论文 §3–5](https://aclanthology.org/2025.emnlp-main.249.pdf) · [固定版本的作者实现](https://github.com/YusaeMeow/Collab-Overcooked/tree/d7ae1aa5e63d8ec076e96ee437fcbbd095278ef4)

在已按项目首页安装 Game Exam 的机器上执行。列目录只需要项目的 Python 环境。运行需要 Linux 容器、Docker Compose v2 和支持命名构建上下文的 BuildKit。

```bash
harbor run --game-suite collab-overcooked --list
harbor run --game-suite collab-overcooked --family level_3 --list
harbor run --game-suite collab-overcooked --offline-smoke --job-name collab-smoke -y
```

真实模型运行前，在宿主环境配置 `COLLAB_API_KEY`。默认模型为作者公开实现支持的 `gpt-4o`。运行时使用当前服务提供的模型版本。可通过 `OPENAI_BASE_URL` 指定角色容器能够访问的服务地址，该服务需要兼容所选模型的上游 chat 接口和重复对话检测用的 `text-embedding-3-small` 接口。上游的通用 vLLM 分支使用其自带的占位 API key，适用于允许该配置的自托管服务。

```bash
harbor run --game-suite collab-overcooked -i boiled_egg -m gpt-4o --job-name collab-egg -y
harbor run --game-suite collab-overcooked -m gpt-4o --job-name collab-full -y
```

每个 Harbor trial 对应一道菜，独立启动作者的 `main.py` 十次。完整套件为六档、每档五道菜，共 300 局。每局使用 `new_env`、两个 `LLMPair`、`fix_task` 和上游默认 120 步上限。独立 verifier 对完整轨迹执行作者的 `time_step.py`（γ=1.5）和 `Evaluation.evaluate`，以整道菜的十局为一组计算 SR、PC、IC、RC。PC 取两名角色 TES 的均值。每道菜的四项指标写入 trial 的 `verifier/reward.json`，作者的详细结果在 `verifier/evaluation_result.json`，原始轨迹在 `artifacts/evidence/raw/`。Harbor 的 agent 名称为 `oracle`，职责仅为等待模拟器结束。实际决策模型及角色策略记录在任务元数据里。

## 隔离与上游差异

- 作者的厨房引擎、调度、角色提示、动作解析、轨迹、参考动作模板与评分代码均从注册清单指定的 Git 提交构建。接入层把原本在进程内执行的规划查询和重复发言相似度调用送入对应角色容器。真实模型使用作者的 `Module.query` 和相似度实现。
- 两个只读、非 root 的角色容器各自只能连接自己的 Unix socket。每个容器收到自己的提示和公共对话，镜像中没有食谱库、参考动作模板、轨迹或 verifier。真实模式中每个角色拥有单独的桥接网络以访问推理服务；这些网络允许出站，并未按域名限制。推理凭据通过只挂载到角色容器的 Compose secret 提供。
- 模拟器、Harbor 主容器和独立 verifier 均关闭网络。模拟器持有食谱并记录轨迹，主容器只读运行状态。Harbor 停止主容器后从模拟器收集可信轨迹，verifier 在独立环境加载参考模板。主容器、角色与模拟器均没有 Docker socket。
- `--offline-smoke` 针对 `boiled_egg` 运行一局，角色容器也关闭网络。固定回答和重复发言测试替身只用于 CI。CI 检查角色提示可见性、镜像中的上游文件哈希、收集来源、verifier 奖励，以及同一固定策略直接运行作者入口所产生的完整轨迹。
- 项目的 `--standard` 模式采用单个 coding agent 的 GameClient 接口。此套件通过同一个 Harbor 启动器选择作者的双角色协议。`overcooked` 目录保留独立的 Overcooked-AI 开发实例。
