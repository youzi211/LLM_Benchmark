# OpenCode / DeepSeek Harness 模型评测与数据集治理评估

评估日期：2026-11-10。状态：代码已接入并通过本地及服务器隔离回归；真实 Agent smoke 已通过，官方 Terminal-Bench 单样本已完整执行 verifier。

本文第 2–9 节保留接入前的核查与设计记录，以下为当前实施状态：

- EvalScope External Agent Bridge 已接入 OpenCode、DeepSeek Harness；Terminal-Bench 4.0 与 SWE-bench Pro V2 使用本地 Harbor task 和独立 verifier，Pro V2 通过新环境补丁重放评分。
- 评测依赖锁定为 Python 3.12、EvalScope 1.14.1、Harbor 0.25.0、swebench 4.1.0；服务器已有 Node 24.11.0、OpenCode 1.19.5、DeepSeek Harness 0.1.5-rc.3。
- 原默认评测与定时组合未调整。Agent 评测由用户人工提交，任务信息与前端数据集分类已接通。
- 验证：服务器 Python 3.12 隔离环境后端 235 项、前端 39 项通过，前端生产构建成功；OpenCode 与 DeepSeek Harness 均已调用真实模型完成工程 smoke 并获得 reward 1.0。官方 Terminal-Bench `photonic-waveguide-routing` 单样本已通过 Harbor、模型 Bridge 和 verifier 的完整执行链路，有效分数为 0%，证明基础设施与评分流程可用。
- 服务器当前正式服务尚未被本轮改动覆盖或重启；隔离验收通过后再同步正式目录。

## 1. 目标与结论

目标：评测同一个模型接入 OpenCode 或 DeepSeek Harness 后完成任务的表现，特别是代码任务；支持固定 Agent 横评不同模型，以及固定模型比较两个 Agent。SWE-bench 路线使用 EvalScope External Agent Bridge，Terminal-Bench 路线使用 Harbor；复用 intelligence 的进程内执行、Job、任务、报告与产物链路。

核心评测条件是：模型 + Agent runner/版本 + 数据集/版本 + 环境/工具 + 提示/Skills + 预算。BFCL、τ²-bench 可作补充工具调用评测，不作为本目标的主线；原生 AgentLoop 也不替代 OpenCode / DeepSeek Harness。

当前三套目标数据已准备，执行适配已实现。推荐分阶段交付：运行依赖与数据治理 → 两个 runner 的固定版本隔离环境 → SWE-bench 小样本 → Terminal-Bench OpenCode → Terminal-Bench DeepSeek Harness → 前端完整验收与扩大规模。现有默认与定时组合保持不变，外部 Agent 组合先人工触发。

## 2. 已核实的环境与适配能力

- 服务器项目：`/data1/yzc/LLM_test/LLM_Benchmark`；Python 3.11.14，EvalScope 1.14.1。
- 数据实体位于当前项目 `data/evalscope_datasets/`，共 18 个数据集目录（原有 15 个及新增 3 个）；旧项目路径仅为兼容软链接。新增数据与校验记录见 [数据准备记录](agent-dataset-preparation.md)。
- 已安装包包含 `evalscope.agent.external.ExternalAgentConfig`，以及 opencode、deepseek_harness runner 和相应 Dockerfile。
- ExternalAgentConfig 具有 framework、environment、environment_extra、timeout、skills_dir、kwargs、bridge 等字段；framework 是 opencode 或 deepseek-harness。
- OpenCode runner 使用 `opencode run`，向 Bridge 发 OpenAI Responses 请求；DeepSeek Harness runner 使用 `dsh --profile headless`，向 Bridge 发 Chat Completions 请求。Bridge 可代理至被测模型的 Chat Completions 接口。
- DeepSeek Harness runner 默认锁定 `0.1.5-rc.2`；OpenCode 默认 npm 安装项没有锁版本，正式评测需要项目自行固定已验证版本及镜像 digest。
- 服务器 PATH 中有 docker、node，没有 opencode、dsh。容器内是否已安装 CLI 尚未检测；Docker 服务、镜像和容器到 Bridge 的连通性尚未验证。
- SWE-bench 外部 Bridge 路线没有因 Python 3.11 而出现已确认的版本阻断；但本次范围包含 Terminal-Bench 4.0，必须满足其 Python >=3.12 和 Harbor >=0.14.0,<1.0.0 约束。建议用现有服务器 Python 3.12 重建并验证服务虚拟环境，再切换主服务，继续进程内执行；不是单独引入 sidecar。

本轮仅只读核查与文档整理，没有安装、构建镜像、调用付费模型或修改服务。

## 3. 接入结构与实施选择

SWE-bench 流程：任务选择模型与 runner → intelligence 构造 TaskConfig.agent_config → EvalScope 启动 Bridge 和逐样本环境中的 CLI → CLI 请求经 Bridge 到被测模型 → CLI 执行工具并反馈 → 基准评分 → 归档结果与轨迹。

Terminal-Bench 流程：任务选择模型与 runner → 项目映射到 Terminal-Bench/Harbor 配置 → Harbor 启动任务环境、CLI 和独立 verifier → CLI 通过项目配置的 provider/代理访问被测模型 → Harbor 评分 → EvalScope 归档。该适配器不能仅依靠 TaskConfig.agent_config 切换到 External Agent Bridge，详见第 9 节。

EvalScope 仍在主服务进程内调用。CLI 作为子进程/容器运行，不另建 EvalScope HTTP sidecar。SWE 路线复用官方两个 Runner；Terminal 路线优先复用 Harbor 已有 Agent，对未支持组合补最小适配。

| 实施范围 | 交付内容 | 取舍 |
| --- | --- | --- |
| 连接验证 | 两个 runner + GSM8K/已有小集 + 任务条件记录 | 快速验证网关、工具链和轨迹，但不能据此声称真实仓库修复能力 |
| 推荐完整范围 | 上述内容 + SWE-bench agentic 小规模任务 + 数据治理/前端/对比 | 能评测用户关注的实际代码工作；增加数据、仓库、镜像准备成本 |

推荐完整范围，按验证步骤逐步开放。先验证 OpenCode 一条链路，再接 DeepSeek Harness；最终两者都纳入，不把第二个 runner 留作无限期后续。

### 执行环境

- 正式评测使用预构建、锁定版本的 Docker 环境，运行时 auto_install=false；Node/npm 与 CLI 预先准备，依赖安装从评分耗时中单独识别。
- DeepSeek Harness 的 Node 版本要求需在镜像中核实；官方说明为 22.19+ 或 24+，不能仅凭基础镜像名字 node:22 就认定已符合。
- 两个 runner 都使用隔离配置目录，不复用宿主已有登录态，避免绕过 Bridge 调用其他模型。以 Bridge/AgentTrace 中的真实模型请求作为链路证据。
- 代码 runner 会自动执行工具。仅向单样本工作区提供任务输入与允许的仓库文件，不挂载项目源码根目录、完整评测题库/答案、models.json、Docker socket 或宿主用户目录。
- Agent 需要访问 Bridge；检查容器到代理、代理到模型网关两段网络。远端 Sandbox 的网络路径另行验证，不能直接套用本机 host.docker.internal 假设。
- SWE-bench 等基准拥有自己的逐样本环境时，遵循适配器契约，ExternalAgentConfig.environment 留空，由基准负责环境；不能额外强塞通用 CLI 容器。需验证该环境里 CLI 可用和依赖准备方式。
- 版本、镜像、工具、网络、Skills 及资源额度一致时才适合横评模型；两个 runner 的差异作为对比条件显式展示。

## 4. 数据集选择与分类治理

### 4.1 推荐用途

| 数据集 | 对本目标的用途 | 接入边界 |
| --- | --- | --- |
| GSM8K、MATH-500 | 已有数据，验证 CLI 调用模型、工具执行、最终答案提取和评分 | 连通验证；不代表编码 Agent 水平 |
| HumanEval / HumanEval+、MBPP / MBPP+ | 小函数代码生成，可先验证外部 CLI 输出与代码评分是否匹配 | 已有数据；必须确认代码提取与测试隔离，不能仅加配置就默认可用 |
| LiveCodeBench | 算法题代码能力 | 已有数据；固定 release 与时间范围，先验证 runner 最终输出适配 |
| SWE-bench Verified Mini Agentic | 仓库级理解、编辑、修复及测试 | 已准备 50 条数据；待准备逐样本运行环境并验证两个 CLI 的补丁及评分链路 |
| SWE-bench Pro V2 | 更完整的代码修复评测 | 已准备 v2 642 条、hard 51 条、v1 731 条及 ca10a60 harness 资源；不同配置有重叠，分别评测，不相加计数 |
| Terminal-Bench 4.0 | 终端综合任务 | 已准备官方 4.0.0 全部 66 个任务；待接本地任务加载、Harbor CLI 模型配置及运行资源 |
| BFCL、τ²-bench | 补充函数调用/业务流程能力 | 第三方适配器控制自身交互；不作为两个 CLI 的默认评测集 |

已有数据优先复用，正式代码效果以实际仓库任务为主。每个“数据集 × runner”组合都需小样本确认指令输入、工作区、最终答案/补丁提取、评分和轨迹，不把全部支持目录一键放行。

### 4.2 四个独立分类维度

1. 能力：代码生成、代码修复、数学、知识、推理、指令遵循、长上下文、图表理解等，可多标签。
2. 输入模态：text、image 等，可多值。
3. 支持的执行方式：standard、external_agent，以及补充的 benchmark_agent/native_agent；外部方式再记录兼容 runner。
4. 就绪状态：数据完整性、依赖/CLI、镜像/环境、模型连接、数据集与 runner 适配验证。

LLM、VLM、Agent 可作快捷视图，不强制互斥。普通 GSM8K 可以同时支持 standard 和 external_agent，数据实体不改名、不复制。

| 已有数据集 | 能力 | 模态或运行说明 |
| --- | --- | --- |
| humaneval、humaneval_plus、mbpp、mbpp_plus、live_code_bench | 代码生成 | 文本；执行测试不等于 Agent 推理 |
| gsm8k、math_500 | 数学、推理 | 文本 |
| ceval、mmlu_pro | 知识、推理 | 文本 |
| bbh | 推理 | 文本、多子集 |
| gpqa_diamond | 科学知识、推理 | 文本 |
| hle | 综合知识、推理 | 适配器默认含图片题；纯文本配置需单独记录 |
| ifeval | 指令遵循 | 文本 |
| longbench_v2 | 长上下文、阅读理解 | 文本，另需上下文长度条件检查 |
| chartqa | 图表理解 | 文本+图片 |

### 4.3 版本与资源记录

- 继续使用 `data/evalscope_datasets/<dataset_id>/` 平铺存放；分类通过元数据完成，不再次移动 18 个数据集。
- 官方名称、子集、版本与评分语义来自 EvalScope 注册表；中文能力映射、兼容组合、精确人工触发默认值集中在 `app/evalscope_defaults.py`，不复制全量官方目录。
- 轻量本地 manifest 记录来源、revision/仓库提交、split、实际子集、文件校验、准备时间、许可证来源。未知历史版本标 unknown，不能推测成最新。
- 镜像由 Docker 管理，在 manifest/运行快照记录 digest；不把镜像实体硬塞进数据目录。包内数据和外部 harness 资源单独标数据来源类型，不能以空目录模拟已下载。
- 目录存在、数据完整、CLI 可运行、Bridge 联通、真实小样本通过分别记录。没有检查就是 unknown；GET 目录不自动安装、拉镜像、下载或产生模型费用。
- 比较身份包含数据 revision、适配器版本、runner/版本、模型、子集、样本范围/limit、提示、Skills、工具、网络与预算；小样本和子集结果明确标注，不能称完整榜单成绩。

## 5. 后端需要改造的位置

| 文件/模块 | 主要改造 |
| --- | --- |
| `app/intelligence/schemas.py` | 增加执行方式和 external_agent 配置：framework、环境预设 ID、单样本 timeout、Skills 预设 ID；限制为 opencode/deepseek-harness |
| `app/intelligence/evalscope_direct.py` | 服务端根据预设生成 ExternalAgentConfig，传入 TaskConfig.agent_config；保留 standard 行为；补齐数据/环境检查 |
| `app/intelligence/runner.py` | 共享提交校验、快照、执行条件归档、恢复条件重跑、有限并发与取消处理 |
| `app/api/routes_intelligence.py` | 增加 catalog、preflight、受控产物读取和服务端重跑入口；保留原本地数据集接口语义 |
| `app/evalscope_defaults.py` | 分类覆盖、已验证 runner/数据集组合、人工触发配置默认值 |
| `app/intelligence/report.py`、overview | 展示模型+runner、运行条件、主指标与覆盖，不新增混合总分 |

关键约束：

- SWE 路线保留 TaskConfig 的 openai_api，framework 控制 CLI。真实模型 URL/Key 来自现有 ModelStore，Bridge 给 CLI 短期 token，不把真实密钥交给页面和任务快照。Terminal 外部 CLI 路线单独生成受控 provider/代理配置，不能假设其继承 TaskConfig 的认证。
- 网页提交受约束配置，不开放任意 command、extra_args、挂载、home_override、Skills 路径或镜像名；管理员准备预设后再供选择。
- 预检基于数据集、runner、环境、目标模型共同判断。工具调用未知应显示未验证，主动模型探测需要明确触发；最终提交及直接 runner 调用复用同一校验。
- 保留原 `/datasets`、`/datasets/local` 的本地接口行为，新增 catalog 返回框架支持项和项目就绪信息。不能再用“同名目录存在”作为唯一判断。
- 检查配置、错误、日志、CLI 输出、EvalScope 落盘配置和轨迹产物的脱敏；产物读取必须限制在任务目录并处理软链接越界，不暴露任意文件下载。
- 原始 AgentTrace 留在 raw_output_dir；normalized_result 只增加少量条件与产物摘要，不复制完整对话。
- 不假定 ExternalAgentConfig 有通用 max_steps：已安装版本主要提供 timeout，CLI 轮次/Token 预算要分别核实支持方式，不能把 NativeAgentConfig 字段直接套用。
- 线程中的第三方运行不能由 asyncio cancel 保证立即终止。必须验证 CLI 进程/容器清理、Bridge 关闭和资源释放；前端区分“取消请求中”与“已停止”。
- 人工组合不改默认/定时策略。套件内部直接调用 runner，外部 Agent 参数若尚未接通应显式拒绝，不能忽略后按 standard 运行。

## 6. 前端对应改造

复用 Vue 3、Element Plus、EvaluationWorkspace 和现有设计系统，不增加一套独立评测后台。

### 新建能力评测

- 第一步选择“标准评测 / 外部 Agent”；外部方式选择 OpenCode / DeepSeek Harness，再选择可兼容数据集。
- 展示当前被测模型和 runner 版本/镜像预设；配置每子集 limit、batch、单样本 timeout 和可选 Skills 预设。
- 保留现有默认组合；外部 Agent 只走显式人工选择，取消自定义空选择回退全部本地数据集的旧规则。
- 运行前展示实际数据集/子集、模式、runner、环境、预检阻断项；费用与Token未取得真实信息时不估造。

### 数据集目录与环境

- 数据集目录按能力、模态、可用执行方式、就绪状态筛选并支持搜索；可以浏览尚未准备项，但不可直接启动。
- 详情显示版本/来源、实际子集、资源状态、兼容 runner 和未就绪原因。筛选不改变已经勾选的集合。
- 评测环境页在 Judge/评分沙箱之外增加“外部 Agent 环境”：CLI/Node 版本、镜像、Bridge 网络检查、检查时间与结果。
- 首期网页不自动安装/下载，提供管理员准备说明与显式重新检测；加载失败、未检测、缺资源、无匹配项分别呈现。

### 任务、结果、重跑和对比

- 列表显示“模型 × runner”，可按标准/OpenCode/DeepSeek Harness 筛选。
- 结果展示任务成功/评分、失败与覆盖、可获得的耗时/Token/工具调用证据及轨迹入口；指标按原始单位与方向展示，不统一强转百分数。
- 首期轨迹按需读取，可先给脱敏原始产物入口；不要把大轨迹塞进任务列表。后续再做逐轮时间线。
- 重跑从完整运行条件恢复；当前前端只传 model_id、datasets，会丢 limit、子集、framework 和预算，必须修复。
- 固定 runner/版本比较模型是主要模式；固定模型比较 runner 是另一模式。不同数据/环境/Skills/预算显示条件差异，不合并成无条件总排名。
- 历史任务缺 runner/模式信息显示“未记录”；标准与外部 Agent 的同名数据集结果不能直接混比。
- 沿用键盘可操作控件、文字状态、标签换行、窄屏折叠详情和亮暗主题。

## 7. 实施步骤与验收

| 步骤 | 验收 |
| --- | --- |
| 1 治理与配置基础 | 18 个集分类正确；空目录不算就绪；表单显式选 framework；标准任务与原默认不变 |
| 2 预构建两个 CLI 环境 | 锁版本、禁运行时安装；隔离配置和输入；容器到 Bridge 到模型链路验证 |
| 3 两个 runner 各跑已有小数据 | GSM8K 1–3 条；Trace 有真实被测模型请求；输出可评分；异常、timeout、取消和资源释放验证 |
| 4 小函数代码适配验证 | 对 HumanEval/MBPP 等确认答案提取和评分，不能将测试答案放进 CLI 工作区 |
| 5 仓库代码任务 | SWE-bench mini agentic 少量任务分别验证两个 runner，留存补丁、测试结果、失败原因和环境身份 |
| 6 前端回归与正式组合 | 新建、目录筛选、预检、轨迹入口、重跑、固定条件对比均可用，公布的是实际运行范围 |

后端测试覆盖配置传递、framework 白名单、就绪校验、密钥脱敏、产物边界、重跑条件、取消与旧任务兼容；前端测试覆盖筛选/选择、条件表单、阻断、重跑和对比。

实施后执行 `LLM_BENCHMARK_SCHEDULER_DISABLED=1 uv run pytest -q`（Windows 使用 PowerShell 设置变量），前端 `npm test`、`npm run build` 和对应 Playwright 流程。真实环境小样本不可由单元测试替代，少量样本也不可当作完整榜单。

本轮未运行上述实施验收，未验证镜像、CLI、真实模型连接和完整任务。数据文件及 SWE Pro harness 资源已准备；主要未决点是运行镜像/网络、Terminal 本地加载及模型连接、补丁提取和评分链路，先做小样本验证再确定全量资源预算。

## 8. 官方依据与版本边界

- [External Agent Bridge 与 Runner](https://evalscope.readthedocs.io/zh-cn/latest/user_guides/agent/bridge.html#runner)
- [SWE-bench](https://evalscope.readthedocs.io/zh-cn/latest/third_party/swe_bench.html)
- [SWE-bench Pro](https://evalscope.readthedocs.io/zh-cn/latest/third_party/swe_bench_pro.html)
- [Terminal-Bench](https://evalscope.readthedocs.io/zh-cn/latest/third_party/terminal_bench.html)
- 已安装 EvalScope 1.14.1：`agent/external/config.py`、`runners/opencode.py`、`runners/deepseek_harness.py`、相关 Dockerfile。

文档 latest 可能变化；实施时以锁定版本源码和实际环境验证为准。官方集成能力不等于本服务器已经跑通，也不保证两个 runner 在所有数据集上行为一致。

## 9. 三套已准备数据的专项适配

以下结论同时对照官网 latest 和本机/服务器可核实源码，不能把 Terminal 的 Harbor 路线套用成 SWE 的 External Bridge 路线。

| 数据集 | OpenCode | DeepSeek Harness | 仍需完成 |
| --- | --- | --- | --- |
| swe_bench_verified_mini_agentic | 复用 ExternalAgentConfig | 复用 ExternalAgentConfig | 传递 agent_config、准备实例镜像/CLI、验证补丁及测试；先各跑 1 条 |
| swe_bench_pro（v2） | 复用 ExternalAgentConfig | 复用 ExternalAgentConfig | 上述能力，加本地 harness 路径、v2 子集、容器资源配置；先各跑 1 条 |
| terminal_bench_v4 | Harbor 0.14.0 已有 OpenCode Agent，但当前 EvalScope 包装未接项目模型配置 | 核查的 Harbor 0.14.0 Agent 注册表没有该项，不能宣称已支持 | 本地任务加载、逐任务模型 provider/代理配置、DeepSeek Agent 适配及 verifier/Compose 资源；先各跑 1 条 |

### 9.1 依赖和环境

- 当前 pyproject 只有 evalscope[perf,sandbox]==1.14.1。新增 Terminal extras 并锁定兼容 Harbor；SWE-bench 官方文档要求 swebench==4.1.0，需补入项目依赖并通过 uv 锁定，而不是仅在服务器临时安装。
- 将主服务运行环境验证到 Python 3.12；测试覆盖原 smoke、intelligence、stress 和 suites。下载工具的隔离 Harbor 环境不代表主服务已具备运行能力。
- 明确区分 ms-enclave 管理的 SWE Pro 环境、SWE-bench 实例环境、Harbor 管理的 Terminal 环境。当前按 CODING 标签统一要求同一 sandbox 的判断应改为按实际执行需求检查。
- SWE 实例镜像有自身工作区和依赖，不能用通用 OpenCode/DeepSeek 镜像覆盖。需要在保留基准环境的前提下预装固定 CLI，或验证受控安装流程；最终记录派生镜像 digest 和 CLI 版本。

### 9.2 SWE Pro 资源参数

- 本地 ca10a60 资源通过 dataset_args.swe_bench_pro.extra_params.swe_bench_pro_repo_path 传递；不能继续依赖运行时 git clone。
- 当前 EvalScopeConfig 及 _task_config_data 仅传 sandbox.manager_config，未支持 sandbox.default_config。需增加受控的 memory_limit、cpu_limit、platform、network_enabled，并同时作用于推理与评分；manager_config 不能替代容器资源参数。
- 分开记录 CLI 推理 timeout、基准测试 eval_timeout、整任务期限。原生循环 max_steps 不等于外部 CLI 预算，按实际 Runner 支持设置。

### 9.3 Terminal 的两个必补连接

1. **本地数据连接**：已安装 Terminal 适配器用 DatasetConfig(name=..., ref=..., download_dir=...) 从 Hub 获取任务，未使用项目注入的通用 local_path。需要通过 EvalScope 扩展点补最小本地加载分支，向 Harbor 传已准备路径的 TaskConfig；保留原任务配置、独立 verifier、Compose、过滤、采样和官方评分，避免复制整个适配器。验证在禁用 Hub 下载时仍能列出并执行指定任务。
2. **被测模型连接**：官方明确只有 terminus-2 自动使用 EvalScope 的模型桥接。opencode 等 CLI 的 api_url/api_key 不会由 TaskConfig 配好；当前 Terminal 包装也没有透传 opencode_config、Agent 版本等项目需要的参数。需按任务解析 ModelStore，配置独立 provider/短期代理凭据，固定 CLI 版本并检查实际请求确实到达所选模型；不能通过进程全局环境变量切换凭据来支持并发任务。

Harbor 0.14.0 OpenCode 实现已有 opencode_config 合并及 ATIF 轨迹能力，优先复用。DeepSeek Harness 应先核实最终锁定 Harbor 是否已有原生实现；若没有，补最小 Harbor Agent，复用任务环境和官方 verifier。也可调查复用 EvalScope External Runner 的扩展方式，但必须验证生命周期与工作区契约，不能只新增 agent_name 字符串。

### 9.4 资源、前端与最终验收

- Terminal 4.0 官方 66 个任务中，11 个含 Compose 服务、3 个要求 H100；Agent 官方时限为 8 小时。先通过 task_names 显式挑选 CPU 可运行任务，不能指望 limit=1 自动避开 GPU。缺少硬件时显示具体不可运行任务，小样本/CPU 子集结果不称完整榜单成绩。
- 数据目录将“数据已准备”“依赖已准备”“运行环境已准备”“模型与 runner 已验证”分别显示，当前 3 个新目录不能直接展示为可运行。框架内部分为 SWE External Bridge 与 Terminal Harbor，用户表单统一选择 OpenCode/DeepSeek Harness，再由后端映射。
- 表单增加 runner、固定版本预设、子集/任务、推理及评分时限、资源额度；任务详情展示失败阶段、补丁/测试/轨迹入口。重跑恢复完整条件，对比按模型、runner、数据版本、资源和预算区分。
- 验收矩阵至少覆盖 3 个数据集 × 2 个 CLI 的 6 条真实链路：每条先 1 个任务，验证请求模型身份、工作区、CLI 执行、评分产物、脱敏、超时和取消清理，再扩大样本。环境错误与任务解答失败分开统计，主分数遵循基准评分定义，同时展示运行覆盖和缺失原因。
- 全量任务需另外核对与官方榜单的 Agent、版本、资源、预算和重复次数是否一致；仅更换成自己的两个 CLI 后的成绩，应标注为项目协议下的评测结果。
