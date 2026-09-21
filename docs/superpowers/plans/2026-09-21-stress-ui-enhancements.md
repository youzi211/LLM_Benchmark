# EvalScope Stress UI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强正式压测的参数、进度、结果和原始产物下载，并完成 Vue 压测页改造。

**Architecture:** 保持 `StressRunner -> EvalScopeStressExecutor` 进程内链路；请求模型显式映射 EvalScope 常用参数，进度从任务输出目录的 `progress.json` 合并到任务摘要。完整结果仍保存在 task 的 `raw_result/raw_output_dir`，新增受目录约束的下载路由；Vue 只消费紧凑归一化结果和按需下载接口。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, EvalScope 1.10.0, pytest, Vue 3, TypeScript, Element Plus, ECharts, Vite

**Spec:** `docs/superpowers/specs/2026-09-21-stress-ui-enhancements.md`

## Global Constraints

- EvalScope 必须进程内执行，不引入 sidecar。
- 保持现有 `/api/stress/*` 请求兼容。
- 原始文件下载必须限制在任务 `raw_output_dir` 内并拒绝目录穿越。
- 不返回或记录模型 API key。
- UI 使用中文说明并满足键盘焦点、状态非纯颜色表达和移动端无横向溢出。

## Review Focus

- `parallel/number` 长度不一致、开环模式误填并发时应给出明确校验错误。
- `multi_turn` 与数据集能力不匹配时应在提交前阻止。
- 缺失、半写入或格式变化的 `progress.json` 不得让任务查询失败。
- 全部请求失败必须显示失败语义，同时保留可下载诊断产物。
- 原始文件接口必须拒绝 `..`、绝对路径、符号链接越界和不存在文件。

---

### Task 1: 压测参数与模式校验

**Files:**
- Modify: `app/stress/schemas.py`
- Modify: `app/stress/runner.py`
- Modify: `app/stress/evalscope_direct.py`
- Modify: `app/evalscope_defaults.py`
- Test: `tests/test_evalscope_stress_schema.py`
- Test: `tests/test_stress_runner.py`

**Interfaces:**
- Produces: `StressMode`, 扩展后的 `StressDefaultRunRequest` / `StressRemoteSubmitPayload`，以及与 EvalScope `Arguments` 同名字段。
- Consumes: 现有模型配置、数据集目录解析和 `EvalScopeStressExecutor.run()`。

- [ ] 先增加请求透传、闭环/开环、多轮及可选 `min_tokens` 的失败测试。
- [ ] 运行定向 pytest，确认因字段缺失或校验行为不符而失败。
- [ ] 最小扩展 schema、默认值和 payload 构建；只向 EvalScope 传递用户设置或官方默认字段。
- [ ] 运行定向测试和现有 stress schema/runner 测试，确认通过。
- [ ] 提交 `feat(stress): expand EvalScope pressure-test parameters`。

### Task 2: 结构化进度、失败语义与丰富结果

**Files:**
- Modify: `app/stress/schemas.py`
- Modify: `app/stress/runner.py`
- Modify: `app/stress/report.py`
- Test: `tests/test_stress_runner.py`
- Test: `tests/test_evalscope_stress_schema.py`

**Interfaces:**
- Consumes: Task 1 的扩展 payload 与任务级 `raw_output_dir`。
- Produces: `StressProgress`、扩展 `StressRunResult`、稳定的全失败判定和错误摘要。

- [ ] 先增加 progress 文件缺失/半写入/正常读取、全失败判定和新指标归一化测试。
- [ ] 运行测试观察预期失败。
- [ ] 实现容错进度解析、任务刷新合并、指标归一化和报告字段。
- [ ] 运行定向测试确认通过。
- [ ] 提交 `feat(stress): expose progress and detailed metrics`。

### Task 3: 原始结果与任务产物安全下载

**Files:**
- Modify: `app/api/routes_stress.py`
- Create: `app/stress/artifacts.py`
- Test: `tests/test_stress_api.py`

**Interfaces:**
- Consumes: `StressTask.raw_result`、`StressTask.raw_output_dir`。
- Produces: `GET /api/stress/tasks/{task_id}/raw-result`、`GET /api/stress/tasks/{task_id}/artifacts`、`GET /api/stress/tasks/{task_id}/artifacts/{path}`。

- [ ] 先增加 JSON 下载、文件清单、文件下载、路径穿越和越界符号链接测试。
- [ ] 运行 API 测试观察 404/接口缺失失败。
- [ ] 实现安全路径解析、清单和 FileResponse/JSONResponse 下载。
- [ ] 运行 stress API 测试确认通过。
- [ ] 提交 `feat(stress): add safe raw artifact downloads`。

### Task 4: Vue 压测工作台改造

**Files:**
- Modify: `frontend/src/views/StressView.vue`
- Modify: `frontend/src/api/evaluations.ts`
- Modify: `frontend/src/types/*`（按现有类型位置）
- Modify: `frontend/src/styles/*`（仅在需要共享样式时）

**Interfaces:**
- Consumes: Task 1-3 的请求字段、结构化进度、扩展结果和下载接口。
- Produces: 基础/高级配置表单、实时进度、指标卡、逐档结果与原始下载区。

- [ ] 先用现有类型检查/构建锁定新增字段的类型缺口，并为可抽取纯函数补充测试（如项目已有前端测试框架）。
- [ ] 实现数据集选择、场景说明、闭环/开环、多轮联动及渐进式高级参数。
- [ ] 实现进度条、成功/失败计数、丰富指标、档位表和产物下载列表。
- [ ] 运行 `npm run build`，修复所有 Vue/TypeScript 错误。
- [ ] 提交 `feat(frontend): enhance stress benchmark workspace`。

### Task 5: 文档、回归与分支审查

**Files:**
- Modify: `docs/api.md`
- Modify: `docs/metric-test-methods.md`
- Modify: `tests/test_docs_coverage.py`（仅当公开路由覆盖断言需要更新）

**Interfaces:**
- Consumes: Task 1-4 的最终 API 和 UI 行为。
- Produces: 用户可复现的参数、进度、结果和下载说明。

- [ ] 更新 API 与压测方法文档，说明参数模式、指标和安全下载。
- [ ] 运行 docs/stress 定向测试、完整 pytest（记录已有基线失败）和 Vue build。
- [ ] 对分支 diff 做安全、兼容性、路径约束和全失败语义自审；重要问题按 TDD 修复。
- [ ] 提交 `docs: document enhanced stress benchmarking`。
