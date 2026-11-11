# Agent 数据集准备记录

日期：2026-11-10。服务器：`test@10.182.17.2`。

数据实体统一存放在当前项目 `/data1/yzc/LLM_test/LLM_Benchmark/data/evalscope_datasets/`。本次准备题目、任务文件和测试脚本资源，不启动模型评测，不改变现有默认和定时组合。

## 数据范围

| EvalScope 名称 | 版本/配置 | 数量 | 数据来源 |
| --- | --- | --- | --- |
| `swe_bench_verified_mini_agentic` | default / test | 50 | ModelScope `evalscope/swe-bench-verified-mini` |
| `swe_bench_pro_v2` | default / hard | 642 / 51 | 官方 Harbor 任务包 |
| `terminal_bench_v4` | 官方 4.0.0 | 66 | Harbor Hub `terminal-bench/terminal-bench@4.0.0` |

Pro V2 的 hard 51 是 default 642 的子集，不相加作为不重复任务总量。保存完整文件哈希与来源版本，不仅记录可变的 master 标签。

## 目录与版本记录

- `data/evalscope_datasets/swe_bench_verified_mini_agentic/default/`：Mini Parquet 数据。
- `data/evalscope_datasets/swe_bench_pro_v2/`：Pro V2 Harbor 任务及 hard 51 清单。
- `data/evalscope_datasets_retired/swe_bench_pro-20261111/{default,hard,v1}/`：原 Pro Parquet 配置的历史归档，已退出当前数据集发现。
- `data/evalscope_datasets/terminal_bench_v4/default/`：Terminal-Bench 任务包；`dataset-lock.json` 记录内容寻址版本。
- `data/evalscope_resources/swe_bench_pro/SWE-bench_Pro-os-ca10a60/`：按旧 Pro 适配器准备的历史 run_script、parser 和 Dockerfile 资源，当前 Pro V2 不依赖此路径。
- `data/evalscope_dataset_manifests/`：本地 SHA-256、文件大小、样本数、来源、资源状态和验证结果。

SWE-bench 原始 Parquet 内容保持不变。为适应项目按顶层目录识别子集，将上游 data 目录整理为顶层 default/hard/v1，并调整 README 的 data_files 路径；原 README 和上游路径/哈希保存在 manifest 中。

EvalScope 本地加载器会删除过时的 `dataset_infos.json`。该文件另行归档在 manifest 的 upstream 目录，不把这一正常清理误报为题目数据损坏。

## 验证方法

- SWE-bench 文件逐项比对 ModelScope 文件列表中的大小和 SHA-256。
- 使用服务器已安装 EvalScope 的 RemoteDataLoader，在 Hugging Face 离线标志开启时读取 Mini 50 条以及 Pro 642/51/731 条，验证实际加载结果。
- Mini 检查任务 ID 唯一性、基础提交与测试列表字段；Pro 检查各配置 ID、必需字段及基础提交。
- Pro 对三组任务逐条调用适配器资源读取函数，确认配套 run_script、parser、base Dockerfile 和 instance Dockerfile 文件存在。
- Terminal-Bench 按官方 4.0.0 清单锁定全部内容哈希；由隔离的 Harbor 0.14.0 下载助手准备任务文件，再传到服务器，核对传输归档和逐文件 SHA-256。

本地下载助手在 outputs 内使用独立环境，不修改项目或服务器主服务依赖。

完成状态：三套新增数据均已在服务器落盘；Terminal-Bench 传输归档 SHA-256 为 `1c3ecc24d5645abf7be938a89ceb02b341270f1c2ad95e67213aea58a42678c3`，解包后验证 66 个任务和 2,505 个清单文件。最终校验摘要保存在服务器 `data/evalscope_dataset_manifests/preparation-summary-2026-11-10.json`。

## 集成与运行状态

- `POST /api/intelligence/tasks` 已接入 `opencode` 与 `deepseek-harness`，可人工触发 Mini、SWE-bench Pro V2 和 Terminal-Bench 4.0；原默认与定时数据集组合不变。
- Terminal-Bench 4.0 与 SWE-bench Pro V2 通过项目内 Harbor adapter 读取已下载任务。Pro V2 的评分会在新的官方任务环境重放 Agent 补丁并执行 verifier。
- OpenCode、DeepSeek Harness、Node 与任务镜像需要提前准备；EvalScope Agent Runtime 目录通过 `agent_runtime_dir` 或环境变量 `LLM_BENCHMARK_AGENT_RUNTIME_DIR` 配置。容器连接模型代理时可配置 `agent_bridge_host` 或 `LLM_BENCHMARK_AGENT_BRIDGE_HOST`。`scripts/prepare_agent_runtime.py` 会把 npm 生成的符号链接改写为启动脚本，因为 EvalScope 打包运行目录时会跳过符号链接，导致容器内 `tools/bin` 为空；Node 入口（`dsh`、`npm`）必须经脚本转成绝对路径，否则相对导入失败。
- SWE-bench 自动构建 Python 基础镜像时默认使用清华 Anaconda 镜像；内网有其他镜像源时可用 `LLM_BENCHMARK_SWEBENCH_MINICONDA_MIRROR` 和 `LLM_BENCHMARK_SWEBENCH_CONDA_MIRROR` 覆盖。
- SWE-bench Mini 实例镜像默认从 `docker.1ms.run/swebench` 拉取；可通过 `LLM_BENCHMARK_SWEBENCH_DOCKERHUB_MIRROR` 指定其他 Docker Hub 镜像站。显式设置的 `dockerhub_username` 优先。
- Harbor 镜像代理按源站处理：`docker.io` 使用 `docker.1ms.run`，`ghcr.io` 使用 `ghcr.1ms.run`。Terminal-Bench 的 Compose 辅助服务通过任务输出目录中的临时 overlay 改写，不修改官方任务文件或内容哈希。
- SWE-bench 任务规格中的 GitHub raw 文件默认通过 `ghfast.top` 代理获取；可通过 `LLM_BENCHMARK_SWEBENCH_RAW_MIRROR` 指定同路径规则的其他代理。
- 最小离线验证先运行 `uv run python scripts/prepare_swebench_images.py --dataset swe_bench_verified_mini_agentic --limit 1`；完整离线评测再将 `--limit` 设为 50。脚本会缓存任务规格文件并预拉实例镜像，完成后用 `--offline-check` 验证缓存和镜像完整性。
- 正式服务已切换到 Python 3.12.14，并安装 EvalScope 1.14.1、Harbor 0.25.0 与 swebench 4.1.0；原有 Python 3.11 环境与配置已保留为回滚备份。
- OpenCode 与 DeepSeek Harness 均已完成真实模型工程 smoke；官方 Terminal-Bench `photonic-waveguide-routing` 单样本已完成 verifier（有效 0%），尚未执行完整任务集或提交榜单结果。Terminal-Bench 任务中的安装脚本、solution 和 verifier 会在 Harbor 容器中执行。

分类方面，三个新增数据集属于代码/终端任务，可用于 Agent 评测。数据目录不向 Agent 整体挂载，特别是参考补丁与隐藏测试不得作为模型输入。

2026-11-11 镜像清点、容量口径、修复与下载限制见 [Agent 镜像容量记录](agent-image-capacity.md)。数据文件就绪、镜像清单可解析、镜像已完整下载是三个不同状态。

2026-11-11 按产品范围移除 Pro V1：页面、任务入口与预热脚本不再接受 `swe_bench_pro`。原目录移至项目内 `data/evalscope_datasets_retired/swe_bench_pro-20261111/` 保存历史来源，不计入当前镜像清单；Pro V2 的任务和 hard 51 子集保留。
