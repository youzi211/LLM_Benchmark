# EvalScope 压测增强设计

## 目标

在保持 EvalScope 进程内执行和现有 `/api/stress/*` 兼容的前提下，补齐官方常用压测参数、结构化进度、完整结果展示与任务原始产物下载，并让 Vue 压测页覆盖短对话、长上下文和多轮对话场景。

## 产品行为

- 基础参数包含数据集、并发、请求数、流式、输入长度和输出长度。
- 高级参数包含 tokenizer、数据集参数、附加请求参数、闭环/开环、请求速率、预热、持续时间、多轮配置、超时及常用生成参数。
- 闭环使用 `parallel` 与 `number`；开环使用 `rate` 与 `number`。多轮数据集必须开启 `multi_turn`。
- 任务进度展示阶段、百分比、当前档位、请求总数、已完成、成功和失败数。
- 结果展示吞吐、延迟、TTFT、TPOT、ITL、token 和多轮指标，并保留逐档表格。
- EvalScope 执行结束但所有请求失败时，任务必须明确标识业务失败，不能只显示成功完成。
- 原始 `raw_result` 可下载；`raw_output_dir` 下文件可以安全列出和下载，路径必须限制在该任务目录内。
- Vue 页面使用渐进式高级参数、清晰帮助文本、可访问状态和响应式布局；旧请求字段继续可用。

## 技术边界

- 不新增 EvalScope sidecar，不复制完整 EvalScope 结果到归一化模型。
- 不暴露 API key、任意服务器路径或任务目录外文件。
- 以已安装 EvalScope 1.10.0 的 `Arguments` 字段为透传依据。
- 后端 FastAPI/Pydantic，前端 Vue 3、Element Plus、ECharts。

