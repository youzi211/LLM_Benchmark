# 文档索引

本项目文档按用途分层，从上手到深入依次如下。接口或行为变更时，请同步更新对应文档和 `README.md` 中的入口。

## 面向上手

| 文档 | 内容 | 适合谁 |
|---|---|---|
| [README.md](../README.md) | 项目总览、安装启动、一键评测与定时计划、Web 控制台、文档入口。 | 所有人，第一站 |
| [部署指南](deployment.md) | Linux/Windows 安装、启动脚本、端口、日志、健康检查、运行目录和安全边界。 | 部署 / 运维 |
| [Web 控制台操作说明](web-console.md) | 内置控制台面板、操作步骤、安全边界和调用的后端接口清单。 | 想用界面而非命令行的用户 |

## 面向接口调用方

| 文档 | 内容 |
|---|---|
| [模型评测与定时评测接口对接说明](model-evaluation-integration.md) | 面向调用方：如何提交一次评测、查询进度与报告、创建一次性或周期性定时评测。 |
| [API 接口文档](api.md) | 所有服务接口、请求/响应结构、错误格式、协议兼容说明和 PowerShell 调用示例。 |

## 面向内部 / 改代码

| 文档 | 内容 |
|---|---|
| [系统架构说明](architecture.md) | 模块分层、数据流、存储结构、suite 执行顺序、扩展点和 Codex 快速排查入口。 |
| [指标测试方法文档](metric-test-methods.md) | 网关 smoke 指标、EvalScope 能力评测、EvalScope 压测和统一报告的测试目标、口径、观测字段和人工关注点。 |
| [自定义数据集接入指南](custom-dataset-guide.md) | 三种接入方式（通用适配器 / 内置数据集 / 自定义 Adapter）、数据格式、Judge 与沙箱配置、常见问题。 |

## 关键约定速查

- **主服务端口**：默认 `8020`（启动脚本 `MAIN_PORT` / `PORT` 默认 `8020`，可用环境变量覆盖）。
- **服务地址**：`http://<主服务地址>:8020`，所有业务接口前缀 `/api`，Web 控制台 `/ui`。
- **suite 执行顺序**：网关接入验收 → EvalScope 压测 → EvalScope 能力评测 → 统一总览报告（先跑压测拿到性能数据，再跑智力评测，避免长时智力评测卡死整条 suite 时丢掉性能结果）。总览报告章节顺序与之一致。
- **`intelligence_limit`**：能力评测每个数据集取前 N 条样本截断；`null` 不限制。**定时计划默认 `200`**（`DEFAULT_SCHEDULED_INTELLIGENCE_LIMIT`），手动 `POST /api/suites/default` 和 `POST /api/suites/quick` 默认不限。
- **不提交**：`data/models.json`（可能含明文 API Key）、`data/evalscope.json`、`data/evalscope_datasets/`、各 `data/*_tasks/`、`reports/`、`outputs/`、`.env`、`.venv/`。提交前用 `git diff-tree --no-commit-id --name-only -r HEAD` 核对。
- **EvalScope 执行模式**：in-process，主服务内直接 `import evalscope`，不启动额外 HTTP 包装服务；代码评分需要的 sandbox 独立运维。
