# Game Exam

**用 coding agent 运行原生游戏 benchmark，统一启动、记录与评分。**

Game Exam 基于 [Embodied First Exam](https://github.com/mll-lab-nu/embodied-first-exam) 的任务封装和 [Harbor](https://github.com/laude-institute/harbor) 执行方式构建。本仓库只包含游戏任务、游戏适配器和它们依赖的公共工具，不包含机器人 benchmark、网站源码、个人配置或历史评测日志。

standard 任务中的模型通过 Harbor 原生 coding agent 阅读 `instruction.md`，在容器内编写并执行程序，通过客户端操作游戏。Collab-Overcooked 使用论文的双角色协议。两类任务都由 Harbor 管理生命周期，并由独立 verifier 根据可信轨迹评分。

> 当前是开发与接入验证版本。冻结任务是已确定环境、实例、seed、观测方式和预算的可复现配置，不等于 benchmark 的全部任务，也不是新的官方排行榜。网站源码在单独的私人仓库维护。

## 目录

- [已接入的游戏](#已接入的游戏)
- [安装与第一次运行](#安装与第一次运行)
- [使用真实模型](#使用真实模型)
- [选择套件、模式、agent 和模型](#选择套件模式agent-和模型)
- [一次任务如何执行](#一次任务如何执行)
- [结果、轨迹与录像](#结果轨迹与录像)
- [评分、时间和可复现性](#评分时间和可复现性)
- [代码结构](#代码结构)
- [新增一个 benchmark](#新增一个-benchmark)
- [测试与常见问题](#测试与常见问题)
- [来源与许可证](#来源与许可证)

## 已接入的游戏

当前接入 7 个 benchmark。5 个提供项目冻结任务，共有 **42 个 standard、1 个 privileged 和 1 个 realtime 配置**。Collab-Overcooked 提供独立的原生双角色套件，覆盖论文的 30 道菜。用 `harbor run --game-suite collab-overcooked --list` 查看任务。Overcooked-AI 另有一个开发实例。[Collab-Overcooked 运行与隔离说明](game_first_exam/benchmarks/collab_overcooked/README.md) · [Overcooked-AI 开发实例](game_first_exam/benchmarks/overcooked/README.md)

| Benchmark | standard | 其他模式 | 主要内容 | 说明 |
|---|---:|---|---|---|
| MiniGrid | 18 | — | 导航、钥匙与门、障碍、记忆、跨越、多个房间 | 6 个任务族，每族 3 个固定 seed |
| Crafter | 3 | 1 realtime | 生存、采集、制造、成就 | 原生 RGB 与成就记录；realtime 是额外的定时交互条件 |
| TextWorld | 9 | — | 文字探索、寻宝、烹饪 | 冻结 `.z8` 游戏，通过原生引擎执行 |
| Baba Is AI | 2 | — | 移动文字、改变规则、解谜 | 基础关卡与复合关卡的最小 smoke 验证 |
| MiniHack | 10 | 1 privileged | Room、River、导航、战斗、Quest、Boxoban | 原生 MiniHack/NLE 环境；Room 另有 privileged 版本 |

套件由 [configs/game_suites/](configs/game_suites/) 定义，可以重叠，数量不能直接相加：

| `--game-suite` | 配置数 | 用途 |
|---|---:|---|
| `smoke` | 3 | MiniGrid、Crafter、TextWorld 各一个标准模式任务 |
| `core` | 30 | MiniGrid 18 + Crafter 3 + TextWorld 9；开发套件 |
| `minigrid` | 18 | MiniGrid 全部当前实例 |
| `crafter` | 4 | standard 3 + realtime 1；运行时应选择模式 |
| `textworld` | 9 | TextWorld 当前实例 |
| `babaisai` | 2 | Baba Is AI smoke |
| `minihack` | 3 | Room/River standard + Room privileged |
| `minihack-balrog` | 8 | 参考 BALROG 选取的原生 MiniHack 任务 |
| `all` | 44 | 所有套件去重后的任务；汇总时应选择一种模式 |

`minihack-balrog` 包含 MazeWalk 9×9、MazeWalk 15×15、Corridor R3、CorridorBattle Dark、Quest Easy、Quest Medium、Boxoban Medium、Boxoban Hard。**使用相同原生环境名称不意味着与 BALROG 的 LLM 输入、prompt、agent、seed 和预算完全相同**，成绩不能直接当作 BALROG 排行榜成绩。

每个游戏的原生版本、观测、冻结参数与已知差异，见对应 [benchmark README](game_first_exam/tasks/)；具体实例以任务的 `tests/instance.json`、`task.toml` 和 `instruction.md` 为准。

## 安装与第一次运行

### 1. 准备运行环境

- Python **3.12–3.14**，建议 3.12；Harbor 固定为 **0.23.0**。
- Git、Docker Engine/桌面版，包含 Compose v2 与 BuildKit。
- 当前游戏任务均为 CPU 环境，不要求 GPU。macOS 需要可用的 Linux Docker 虚拟机；Linux 可直接运行 Docker。
- 首次构建需要访问基础镜像、Python/系统依赖及部分上游源码。源码体积不代表镜像占用；镜像和 `jobs/` 应预留数 GB 以上空间。
- files-only 镜像会在本地按冻结源码组装。建议使用 **containerd image store**（如 Docker Engine 29/支持该功能的 Docker Desktop）；旧 classic store 可能仍尝试从注册表拉取 `@sha256` 引用，详见 [镜像说明](docs/protocol/running.md#镜像与平台)。

```bash
git clone https://github.com/LAMDA-NeSy/Game_exam.git
cd Game_exam

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

docker version
docker compose version
```

也可使用 `uv` 管理环境。请从本仓库安装：安装同名上游包不会包含这里的游戏任务和选择逻辑。安装后 `harbor` 保留原生命令，并增加 `--game-suite` 等任务选择参数；`game-exam run ...` 是同一入口的别名。

### 2. 先检查任务，不启动模型

```bash
harbor run --game-suite minihack --standard --list
harbor run --game-suite minihack-balrog --standard --list

# 验证全部套件、冻结摘要、文件绑定、监控和隔离配置
python ci_checks/check-games.py
```

`--list` 做配置预检和任务列表输出，不构建镜像、不启动游戏、不调用模型。

### 3. 用 oracle 跑通 MiniHack Room

```bash
harbor run --game-suite minihack --standard --family room \
  -c configs/harbor/oracle.json \
  --plugin game_harbor:GameRecords \
  --job-name room-oracle
```

此命令会准备镜像、复制冻结任务、启动容器、执行参考程序并收集与评分。**oracle 是参考解，不是模型成绩**，无需模型 API key。第一次运行可能主要耗时在镜像构建；后续可利用缓存。再次运行请换一个 `--job-name`，保留前一次记录。

## 使用真实模型

### DeepSeek + Codex 示例

这里复用 Harbor 的原生 Codex agent。示例配置固定 Codex CLI 版本、DeepSeek provider 和工具权限；密钥从环境读取，不写入 JSON 或仓库。

先为当前终端设置 `OPENAI_API_KEY`，其值应是 **DeepSeek API key**。该配置使用 Codex 的通用密钥变量名，不代表调用 OpenAI。也可以复制 `.env.example` 为 `.env` 并在本地填写；`.env` 被 Git 忽略，不要将其提交。

```bash
# 已在本地配置 OPENAI_API_KEY 后执行；这一步会产生模型 API 费用
harbor run --game-suite minihack --standard --family room \
  -c configs/harbor/codex-deepseek.json \
  --plugin game_harbor:GameRecords \
  --job-name room-deepseek
```

该 profile 使用 `deepseek-flash`、Codex `0.167.1`，通过原生 Responses HTTP 接口请求 `https://api.deepseek.com`。关闭 WebSocket、网络搜索、应用连接器、插件和图像生成，保留容器内程序执行和游戏客户端调用。它不是自建模型代理。模型别名可能随 provider 更新，不能当作不可变权重版本。

Crafter realtime：

```bash
harbor run --game-suite crafter --realtime \
  -c configs/harbor/codex-deepseek.json \
  --plugin game_harbor:GameRecords \
  --job-name crafter-realtime-deepseek
```

MiniHack Room privileged：

```bash
harbor run --game-suite minihack --privileged \
  -c configs/harbor/codex-deepseek.json \
  --plugin game_harbor:GameRecords \
  --job-name room-privileged-deepseek
```

其他 agent/model 直接用 Harbor 的原生参数，例如：

```bash
# 将 YOUR_MODEL_ID 换成所选 agent/provider 实际支持的模型名，并配置对应认证
harbor run --game-suite minihack --standard --family room \
  -a claude-code -m YOUR_MODEL_ID --job-name room-other-agent
```

这只是参数用法，不宣称任意 agent 与任意模型可以组合。认证、API 兼容性和工具能力由相应原生 agent 决定。查看 [原生配置说明](configs/harbor/README.md)。

**配置合并注意：**使用一个 agent profile 即可。在 Harbor 0.23.0 中重复 `-c` 会追加 agent/task 列表；`-a` 会替换配置里的整个 agent，包括其工具设置，`-m` 单独出现也不是该版本的 profile 模型覆盖方式。需要修改模型时，复制并编辑 profile，或明确使用完整的 `-a/-m/--ak` 参数。

## 选择套件、模式、agent 和模型

四者独立：套件决定选哪些任务，模式决定任务如何与 agent 交互，agent 决定工具执行方式，模型负责该 agent 的决策。模式参数只筛选已实现的任务，不会自动生成一种新模式。

| 模式 | 执行方式 | 当前覆盖 |
|---|---|---|
| `standard` | agent 通过客户端操作可信模拟器，按动作推进；对 live episode 评分 | 5 个游戏、42 个配置 |
| `privileged` | agent 可本地探索和规划；最终动作序列由独立 verifier 重新执行 | MiniHack Room |
| `realtime` | 首次有效动作计划启动固定 tick；程序与模型思考期间游戏继续推进 | Crafter survival i01 |

```bash
# 只列 8 个 MiniHack 任务中的 Quest
harbor run --game-suite minihack-balrog --standard -i '*quest*' --list

# 限制任务数量（不是重复次数）
harbor run --game-suite minigrid --standard -l 1 --list

# 所有标准模式游戏配置
harbor run --all --standard --list
```

也支持 `--benchmark`、`--family`、`-x` 排除名称、`-p` 目录范围。`--game-suite` 不与 `--core/--all` 同时使用。原生 `harbor run -p <自包含任务目录>`、`harbor run -c <自有配置>` 在不使用游戏选择参数时仍直接交给 Harbor；这些入口不会替你组装 files-only 镜像。

可将准备和执行分开：

```bash
python scripts/prepare_games.py --suite minihack --family room \
  --output jobs/prepared/room.json
# room 家族含不同模式；需要单一模式时优先使用上面的 --standard/--privileged 主入口
harbor run -c jobs/prepared/room.json -c configs/harbor/oracle.json
```

预设配置为一次尝试、串行执行、不自动重跑。`GameRecords` 拒绝将不同模式混在同一个汇总报告里。

## 一次任务如何执行

以 MiniHack Room standard 为例：

1. `scripts/efe.py` 解析套件与筛选条件，保留 Harbor 的 agent/model/config 参数。
2. `scripts/prepare_games.py` 调用 `game_preflight.py` 检查 schema、实例一致性、评分定义、资源配置、镜像文件绑定和 `DIGEST`，然后在 `jobs/prepared/` 生成自包含任务副本。
3. Harbor 根据 `task.toml` 和 Docker Compose 创建 agent、sim 和资源监控环境，把该任务的 `instruction.md` 交给 coding agent。
4. 模型可写控制脚本、执行脚本、查看结果并修改程序。`game_client.py` 发起请求，`server.py` 检查顺序、去重和预算，`adapter.py` 把动作转给原生 MiniHack/NLE。
5. sim 保存原生结果、动作轨迹及录像。Agent 结束或到期后按冻结的收集顺序封存证据。
6. Harbor 在隔离 verifier 中运行 `tests/test.sh`，调用公共 grader 和 MiniHack 专属指标规则，输出分数。
7. Harbor 保存原始运行记录；可选 `GameRecords` 插件补充镜像来源、完整性检查和派生汇总。

模型没有被要求每轮只返回一个 JSON 动作；它可以写持续运行的程序。客户端的一次典型调用如下，**需在任务容器中执行**：

```python
from game_client import GameClient

client = GameClient()
spec = client.spec()                # 协议、动作、能力与预算等声明
obs = client.observe()              # 当前 step、done、observation 等

if not obs['done']:
    # Room 的任务说明定义了合法动作 N；其他游戏须查各自 instruction/spec。
    reply = client.step('N', expected_step=obs['step'])
    print(reply['step'], reply['done'])
```

MiniHack Room standard 暴露配置中规定的玩家中心 **9×9 局部观测**；不应将审计录像或原生屏幕缓存当作额外的模型观测。其他游戏的文本、符号数组、RGB 等以各自 observation profile 为准。详见 [Room instruction](game_first_exam/tasks/minihack/minihack-room-i01-standard/instruction.md)。

## 结果、轨迹与录像

默认结果保存在 `jobs/<job-name>/`。`--jobs-dir` 可以修改 Harbor 结果位置，但 `jobs/prepared/` 的冻结副本也应保留，`lock.json` 会引用它们。

```text
jobs/<job-name>/
├── config.json                 # Harbor 实际解析后的配置
├── lock.json                   # 任务和运行锁定信息
├── result.json                 # Harbor 整个 job 的结果
├── <trial>/
│   ├── result.json             # 单次尝试：结果、token 使用、异常等
│   ├── agent/                 # agent 工具调用与执行记录
│   ├── verifier/reward.json    # 验证后的评分和错误标记
│   └── artifacts/
│       ├── app/output/        # 模型脚本和其输出
│       └── data/              # live 任务的可信轨迹、final.json、replay.mp4 等
├── game-provenance.json        # 启用 GameRecords 时生成
├── runtime-images.json        # 实际容器镜像标识与覆盖状态
└── game-report/                # 派生 REPORT.md、summary.json、episodes.csv
```

不同模式的证据位置以任务声明为准，privileged 的重放证据由 verifier 产生。失败、极短运行或渲染失败时不能保证有可播放录像；检查 `recording.json` 和对应错误，不能把没有录像解释为成功。

```bash
harbor view jobs
```

录像编码帧率不一定等于真实游戏时钟；例如 Crafter 的 0.2 秒 tick 与录像播放速度不一定一致。预算分析应看计时字段和轨迹，不要用视频长度代替墙钟耗时。

## 评分、时间和可复现性

| 游戏 | 主指标 | 同时保留的信息 |
|---|---|---|
| MiniGrid / Baba Is AI | 原生目标是否成功 | reward、步数、原生终局 |
| TextWorld | 原生 score / max_score | 原生得分、胜负、步数 |
| MiniHack | 完成 100，未完成 0 | 原生 return、end status、动作数；100 是分数，不是 100 步 |
| Crafter | 单局成就比例；跨局另计算成就成功率的 Crafter score | 22 个成就、原生 return、存活状态；木镐是辅助目标 |

普通 reducer 按任务族汇总，Crafter 使用独立、带版本的成就 reducer。缺失局、重复局、环境故障和有效失败分开处理；模型未完成应计为有效失败，不能随意删掉。单局成就比例不是官方完整评测集的总分。

有两个不同的限制：

- **环境动作限制**来自冻结实例和原生任务，限制游戏推进次数。
- **Agent 墙钟限制**来自 `task.toml` 的 `[agent].timeout_sec`，由 Harbor 约束，包括准备、模型调用和工具等待。资源监控在 `/run/rcb-limits/usage.json` 提供剩余时间。

Crafter realtime 的服务预算从首次请求计时；游戏运动从首次有效 `submit` 开始。`preparation_s` 记录准备时间、`clock_s` 记录游戏时钟，二者都不会暂停外层 Harbor 截止时间。`submit` 接受计划不等于动作执行完成，更不等于原生操作成功。持续控制程序需要查看 `step`、`plan_end_step` 和 `done`。参见 [realtime instruction](game_first_exam/tasks/crafter/crafter-survival-i01-realtime/instruction.md)。

可复现性来自实例、seed、依赖/上游源码版本、files-only 镜像摘要、任务 `DIGEST`、Harbor 配置及实际运行镜像。MiniHack 还固定原生模拟器日历，以免 NetHack 日期机制改变同 seed 行为，真实预算时间不随之伪造。模型 provider 别名、系统包源和不同宿主机仍可能变化；不承诺所有机器、所有模型回放逐字一致。

资源监控默认可能仅记录，是否启用额外强制限制以配置和结果里的 `resource_enforced` 为准。模型 token/cost 从原生 agent 记录取得；`cost_usd: null` 代表未提供，不能解释为免费。评测不会因为代码公开就自动使用个人 API key。

## 代码结构

```text
Game_exam/
├── game_first_exam/
│   ├── runtime/               # 公共服务、客户端、契约、配置、评分、录像、reducer
│   │   └── modes/             # privileged / realtime 的执行与验证
│   ├── benchmarks/<game>/    # adapter、instance_schema、metric_rules、原生依赖
│   ├── tasks/<game>/<task>/  # 冻结 Harbor 任务
│   ├── images/               # 游戏 files-only 镜像清单
│   └── tests/                # 公共及原生游戏测试、固定依赖环境
├── shared/connection/         # 从上游复用的就绪等待和连接处理
├── images/                    # 共用 connection-files 与 monitor；没有机器人镜像
├── configs/                   # 游戏 schema 注册、套件、Harbor 原生配置
├── scripts/                   # 任务选择、准备、规范化、镜像与报告工具
├── ci_checks/                 # 游戏配置、摘要、资源、隔离等检查
├── docs/                      # 框架、运行模式、写任务说明的模板
└── .github/workflows/games.yml
```

原版可复用的部分是 Harbor 执行、任务格式、连接等待、时间截止、资源监控、文件封装和验证隔离。游戏专属部分是原生环境适配、观测输出、动作映射、原生结束语义和指标。公共 grader 校验可信封存证据及游戏语义，并非对整个任意轨迹的防篡改重放证明；其信任边界是隔离 sim、收集流程和 verifier。

为了保持历史任务身份、镜像内容与追溯关系，部分冻结字段仍使用 `embodied-first-exam/...` 或 `ghcr.io/mll-lab-nu/efe:...` 名称。**这些是兼容标识，不表示本仓库还包含具身任务，也不表示镜像已发布到 LAMDA-NeSy。**

## 新增一个 benchmark

建议先接一个基础任务和一个有代表性的复杂任务，跑通后再扩展，不要先重写公共服务。

1. **检查原生环境。**确认创建/reset/step/close、动作集合、奖励、终止和截断、观测可见性、seed、依赖和许可证。记录必须适配的地方，保持原生设置尽可能不变。
2. **编写薄 adapter。**放在 `game_first_exam/benchmarks/<name>/adapter.py`，实现 [公共契约](game_first_exam/runtime/contracts.py)：

   | 接口 | 作用与要求 |
   |---|---|
   | `__init__(instance, assets)` | 根据冻结配置构造一次环境 |
   | `spec()` | 声明动作、能力与观测格式 |
   | `observe()` | 返回允许模型看到的信息；不改变状态/RNG |
   | `step(action)` | 执行一个原生动作，返回增量 reward、terminated、truncated |
   | `metrics()` / `success()` | 导出原生指标和明确的成功条件 |
   | `fingerprint()` | 内部审计状态摘要；不得当作模型额外观测 |
   | `frame()` | RGB uint8 数组或 None，用于记录；不改变状态/RNG |
   | `close()` | 释放资源 |

3. **加专属配置和评分校验。**实现 `instance_schema.py`、`metric_rules.py`，在 `configs/game_benchmarks.toml` 注册可信路径。未知字段、版本、reducer 必须拒绝。只有原生汇总确实不同才新增 reducer，不在 runner 中累加游戏名称分支。
4. **冻结任务。**按现有任务创建 `instruction.md`、`task.toml`、`environment/`、`tests/`、`solution/`、README。实例和资产由 sim 与 verifier 各持一份；参考解仅供 oracle/验证使用，不能复制进 agent 可读镜像。
5. **组装镜像与套件。**创建 files-only 镜像清单、版本和摘要；在 `task_conventions.py` 注册任务前缀和目录，在资源规则中声明上限，在 `configs/game_suites/` 注册实际任务。任务运行时只依赖自己的文件和冻结镜像。
6. **编写任务说明。**参考 [说明模板](docs/templates/game-standard/instruction.md.template) 和 [写作指南](docs/templates/game-standard/README.md)。写清场景与目标、真实观测、合法动作、函数参数与返回例子、计分和限制。不要泄露隐藏状态或给出参考路线。
7. **验证。**比较原生环境与 adapter 的逐步观测/奖励/终局；测试相同 seed、只读观察、非法动作、原生截断和公共预算。运行公共测试、专属固定环境测试、预检，再用 oracle 和失败对照跑完整 Harbor 链路。真实模型测试应另行明确模型、预算和费用。

```bash
# 修改任务后规范化并刷新摘要
python scripts/task_conventions.py game_first_exam/tasks/<game>/<task>
python ci_checks/check-games.py
```

只添加同一游戏的新任务通常不需要改公共 server/client/grader。新增 observation profile 或原生设置时，需要同步专属 schema、任务说明及测试；不能只改任务名称。

## 测试与常见问题

公共测试和每个游戏使用固定的独立依赖镜像；无需模型 key：

```bash
docker build -f game_first_exam/tests/envs/common.Dockerfile -t game-tests:common .
docker run --rm -v "$PWD:/repo:ro" game-tests:common \
  bash game_first_exam/tests/run.sh common

# 将 common 换成 minigrid / crafter / textworld / babaisai / minihack
# Harbor 选择、配置合并、锁定和报告测试：
python game_first_exam/tests/test_game_harbor.py
```

GitHub Actions 执行静态检查、公共测试、5 个原生 adapter 环境及 Harbor 集成测试；不调用真实模型，不部署网站，不发布 PyPI 包或镜像。

- **`harbor` 不识别 `--game-suite`：**确认当前环境执行过 `pip install -e .`，并检查 `which harbor`。也可用 `game-exam run ...`；单独安装 Harbor 不包含本仓库选择逻辑。
- **选不到任务：**先 `--list`；只有 Room 有 MiniHack privileged，只有 Crafter i01 有 realtime。模式不匹配会拒绝启动。
- **构建/拉取失败：**区分 Docker、包源、原生引擎构建和模型 API。成功调用模型不代表 PyPI/GitHub 下载正常；固定镜像引用也不代表已经缓存在你的机器。
- **换模型配置失效：**检查 Harbor 的配置合并规则和最终 `config.json`，避免叠加两个 agent profile。
- **realtime 无动作：**查看 agent 工具记录和控制程序是否仍存活；按 instruction 建立独立后台进程并检查进度。单独使用 `nohup ... &` 不保证在所有 agent 的工具生命周期里继续运行。
- **模型失败但参考解成功：**这可能是感知、规划或程序错误。先查可信轨迹和终局，不能仅靠模型最后的文字自述判断环境正确或错误。
- **100 分和 100 步：**MiniHack 的 100 是完成分数，动作限制另看实例和 instruction。

## 来源与许可证

本仓库保留上游 MIT 许可证及版权声明。共享代码来源、移除范围和第三方依赖说明见 [UPSTREAM.md](UPSTREAM.md)。各原生游戏、引擎和随附资源继续遵循各自许可证；本仓库的 MIT 许可不替代第三方许可。

这是面向游戏的派生框架，不是 Embodied First Exam、BALROG 或各原生 benchmark 的官方发行版，也不将本地验证分数表述为其官方排行榜结果。

本次纯游戏仓库整理的本地验证：98 项回归通过，独立安装及 MiniHack Room oracle 全流程通过；短参考运行的资源采样限制详见 [验证记录](docs/VALIDATION.md)。这不是模型排行榜成绩。
