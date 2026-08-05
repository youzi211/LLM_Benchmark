# LLM Report Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fixed-model LLM analysis and a Chinese-friendly dashboard-style Markdown report for benchmark task results.

**Architecture:** Metrics remain the source of truth. After probes finish, build a bounded `ReportFactPack`, call the configured analysis model, parse a structured `ReportAnalysis`, then render an enhanced Markdown report. Analysis failures are shown in the report but never change the benchmark task status.

**Tech Stack:** Python 3.11+, Pydantic v2, existing async adapters, pytest, uv.

---

## File Structure

- Create `app/reports/schemas.py`: Pydantic models for fact packs and analysis output.
- Create `app/reports/facts.py`: deterministic extraction of status counts, core observations, focus suggestions, and raw excerpts from `TaskResult`.
- Create `app/reports/analyzer.py`: fixed analysis-model lookup, prompt construction, adapter call, JSON extraction/parsing, failure fallback.
- Modify `app/storage/model_store.py`: object-form `models.json`, legacy list-form compatibility, `get_analysis_model_id`, `set_analysis_model_id`.
- Modify `app/core/models.py`: persist `analysis_model_id` and `analysis` on `TaskResult`.
- Modify `app/core/runner.py`: build facts, run analyzer, pass facts/analysis to report writer.
- Modify `app/reports/markdown.py`: render LLM summary, dashboard, metric table, details, and appendices.
- Tests: update `tests/test_models_api.py`, `tests/test_report_localization.py`, `tests/test_runner_fake_upstream.py`; create `tests/test_report_facts.py`, `tests/test_report_analyzer.py`.

---

### Task 1: ModelStore supports `analysis_model_id`

**Files:**
- Modify: `D:\lakala\LLM_Benchmark\app\storage\model_store.py`
- Test: `D:\lakala\LLM_Benchmark\tests\test_models_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_models_api.py`:

```python
def test_model_store_reads_and_preserves_analysis_model_id(tmp_path):
    from app.core.models import ModelConfigCreate
    from app.storage.model_store import ModelStore

    store = ModelStore(tmp_path / "models.json")
    store.create(ModelConfigCreate(id="report-analyzer", name="报告分析模型", protocol="chat_completions", base_url="http://analysis.local/v1", api_key="test-analysis-key", model="analysis-model"))
    store.set_analysis_model_id("report-analyzer")

    reloaded = ModelStore(tmp_path / "models.json")
    assert reloaded.get_analysis_model_id() == "report-analyzer"
    assert reloaded.get("report-analyzer").model == "analysis-model"


def test_model_store_legacy_list_form_has_no_analysis_model_id(tmp_path):
    import json
    from app.storage.model_store import ModelStore

    path = tmp_path / "models.json"
    path.write_text(json.dumps([{"id":"legacy-model","name":"Legacy Model","protocol":"chat_completions","base_url":"http://legacy.local/v1","api_key":"test-legacy-key","model":"legacy-upstream","timeout_seconds":60,"enabled":True,"declared_context_tokens":None,"declared_max_output_tokens":None,"concurrency_levels":[1,5,10,20]}]), encoding="utf-8")

    store = ModelStore(path)
    assert store.get_analysis_model_id() is None
    assert store.get("legacy-model").model == "legacy-upstream"
```

- [ ] **Step 2: Verify failing test**

Run:

```powershell
uv run pytest tests\test_models_api.py::test_model_store_reads_and_preserves_analysis_model_id tests\test_models_api.py::test_model_store_legacy_list_form_has_no_analysis_model_id -q
```

Expected: fails because `set_analysis_model_id` is missing or legacy list-form is unsupported.

- [ ] **Step 3: Implement storage compatibility**

In `app/storage/model_store.py`, add these helpers to `ModelStore` and update `_load`/`_save` to use them:

```python
    def _load_document(self) -> dict:
        data = read_json_file(self.path, {"models": []})
        if isinstance(data, list):
            return {"models": data, "analysis_model_id": None}
        return {"models": data.get("models", []), "analysis_model_id": data.get("analysis_model_id")}

    def _save_document(self, models: list[ModelConfig], analysis_model_id: str | None) -> None:
        payload = {"models": [m.model_dump(mode="json") for m in models]}
        if analysis_model_id:
            payload["analysis_model_id"] = analysis_model_id
        write_json_file_atomic(self.path, payload)

    def _load(self) -> list[ModelConfig]:
        return [ModelConfig.model_validate(item) for item in self._load_document().get("models", [])]

    def _save(self, models: list[ModelConfig]) -> None:
        self._save_document(models, self.get_analysis_model_id())

    def get_analysis_model_id(self) -> str | None:
        return self._load_document().get("analysis_model_id")

    def set_analysis_model_id(self, model_id: str | None) -> None:
        models = self._load()
        if model_id is not None and not any(m.id == model_id for m in models):
            raise KeyError(f"model_not_found:{model_id}")
        self._save_document(models, model_id)
```

Keep existing `list/get/create/update/delete` methods unchanged except for their use of `_save`.

- [ ] **Step 4: Verify Task 1**

Run:

```powershell
uv run pytest tests\test_models_api.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add app\storage\model_store.py tests\test_models_api.py
git commit -m "feat: 支持报告分析模型配置"
```

---

### Task 2: Add report schemas and fact extraction

**Files:**
- Create: `D:\lakala\LLM_Benchmark\app\reports\schemas.py`
- Create: `D:\lakala\LLM_Benchmark\app\reports\facts.py`
- Test: `D:\lakala\LLM_Benchmark\tests\test_report_facts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_report_facts.py`:

```python
from app.core.models import MetricResult, TaskResult, utc_now
from app.reports.facts import build_report_fact_pack, metric_core_observation_text


def test_report_fact_pack_counts_status_and_extracts_context_key_facts():
    started = utc_now()
    result = TaskResult(task_id="task_fact_pack", status="completed", model_id="minimax-m3-ark-real", model_config_name="MiniMax-M3 火山方舟兼容接口", upstream_model_name="minimax-m3", protocol="chat_completions", plan_id="gateway_baseline_v1", metric_ids=["connectivity", "context_length"], started_at=started, finished_at=started, duration_ms=127.5, results=[
        MetricResult(metric_id="connectivity", metric_name="连通性", status="completed", summary="连通性探测完成", observations={"http_status": 200, "latency_ms": 123.4, "content_present": True}),
        MetricResult(metric_id="context_length", metric_name="上下文长度", status="error", summary="上下文存在未通过点", observations={"declared_context_tokens":1048576,"observed_accepted_max_prompt_tokens":943718,"observed_marker_found_max_prompt_tokens":943718,"first_http_error_point":1048576,"first_marker_miss_point":None,"point_results":[{"requested_approx_tokens":943718,"accepted_by_api":True,"retrieval_ok":True,"http_status":200,"usage_prompt_tokens":817455},{"requested_approx_tokens":1048576,"accepted_by_api":False,"retrieval_ok":False,"http_status":429,"error":{"code":"AccountQuotaExceeded","message":"quota"}}]}, errors=[{"code":"context_acceptance_failed","message":"1024K failed"}]),
    ])

    facts = build_report_fact_pack(result)

    assert facts.status_counts.total == 2
    assert facts.status_counts.completed == 1
    assert facts.status_counts.error == 1
    context = next(item for item in facts.metric_facts if item.metric_id == "context_length")
    assert context.key_facts["observed_accepted_max_prompt_tokens"] == 943718
    assert context.important_raw_excerpt[0].label == "context_point_results"
    assert len(context.important_raw_excerpt[0].data) == 2


def test_metric_core_observation_text_returns_chinese_summary():
    item = MetricResult(metric_id="stream_spec", metric_name="流式规范性", status="completed", summary="流式规范观测完成", observations={"http_status": 200, "ttft_ms": 653.2, "done_present": True, "finish_reason_present": True, "stream_usage_present": False})

    text = metric_core_observation_text(item)

    assert "HTTP 200" in text
    assert "TTFT 653.2 ms" in text
    assert "[DONE]：是" in text
```

- [ ] **Step 2: Verify failing import**

Run:

```powershell
uv run pytest tests\test_report_facts.py -q
```

Expected: fails because `app.reports.facts` is missing.

- [ ] **Step 3: Implement schemas**

Create `app/reports/schemas.py` with:

```python
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class ReportTaskFacts(BaseModel):
    task_id: str
    model_id: str
    model_config_name: str | None = None
    upstream_model_name: str | None = None
    protocol: str | None = None
    plan_id: str
    duration_ms: float | None = None

class ReportStatusCounts(BaseModel):
    total: int = 0
    completed: int = 0
    error: int = 0
    skipped: int = 0

class ReportRawExcerpt(BaseModel):
    label: str
    data: Any

class ReportMetricFact(BaseModel):
    metric_id: str
    metric_name: str | None = None
    status: str
    summary: str
    core_observation: str
    suggested_focus: str
    key_facts: dict[str, Any] = Field(default_factory=dict)
    important_raw_excerpt: list[ReportRawExcerpt] = Field(default_factory=list)

class ReportFactPack(BaseModel):
    task: ReportTaskFacts
    status_counts: ReportStatusCounts
    metric_facts: list[ReportMetricFact] = Field(default_factory=list)

class ReportAnalysisMetricNote(BaseModel):
    metric_id: str
    note: str
    severity: Literal["info", "low", "medium", "high"] = "info"

class ReportAnalysis(BaseModel):
    analysis_status: Literal["completed", "skipped", "error"]
    analysis_model_id: str | None = None
    one_sentence_summary: str | None = None
    overall_assessment: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    metric_notes: list[ReportAnalysisMetricNote] = Field(default_factory=list)
    error_message: str | None = None
    raw_excerpt: str | None = None

def skipped_analysis(message: str) -> ReportAnalysis:
    return ReportAnalysis(analysis_status="skipped", error_message=message)

def errored_analysis(message: str, analysis_model_id: str | None = None, raw_excerpt: str | None = None) -> ReportAnalysis:
    return ReportAnalysis(analysis_status="error", analysis_model_id=analysis_model_id, error_message=message, raw_excerpt=raw_excerpt)
```

- [ ] **Step 4: Implement fact builder**

Create `app/reports/facts.py` with functions named exactly: `build_report_fact_pack`, `metric_key_facts`, `metric_raw_excerpts`, `metric_core_observation_text`, `suggested_focus_text`. Implement per spec section 9. Required behavior:

```python
# context_length must include these keys when present:
["declared_context_tokens", "observed_accepted_max_prompt_tokens", "observed_marker_found_max_prompt_tokens", "first_http_error_point", "first_marker_miss_point", "stopped_after_hard_error"]

# context raw excerpt must compact point_results to these fields:
["requested_approx_tokens", "accepted_by_api", "retrieval_ok", "http_status", "usage_prompt_tokens", "error"]

# stream_spec core text must include:
"HTTP {http_status}，TTFT {ttft_ms} ms，[DONE]：是/否，finish_reason：是/否，stream usage：是/否"
```

Use `format_metric_label` when `metric_name` is missing.

- [ ] **Step 5: Verify Task 2**

Run:

```powershell
uv run pytest tests\test_report_facts.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add app\reports\schemas.py app\reports\facts.py tests\test_report_facts.py
git commit -m "feat: 构建报告事实包"
```

---

### Task 3: Add fixed-model report analyzer

**Files:**
- Create: `D:\lakala\LLM_Benchmark\app\reports\analyzer.py`
- Test: `D:\lakala\LLM_Benchmark\tests\test_report_analyzer.py`

- [ ] **Step 1: Write failing tests**

Create tests for: `extract_json_object`, success with configured model, missing config skipped, invalid JSON error. Use a fake adapter returning `AdapterResponse`. The success assertion must check:

```python
assert analysis.analysis_status == "completed"
assert analysis.analysis_model_id == "report-analyzer"
assert "不要判断模型是否允许上线" in adapter.requests[0].system_prompt
assert "test-analysis-key" not in adapter.requests[0].prompt
```

- [ ] **Step 2: Verify failing import**

Run:

```powershell
uv run pytest tests\test_report_analyzer.py -q
```

Expected: fails because `app.reports.analyzer` is missing.

- [ ] **Step 3: Implement analyzer**

Create `app/reports/analyzer.py` with:

```python
from __future__ import annotations
import json, re
from collections.abc import Callable
from pydantic import ValidationError
from app.adapters.base import BaseAdapter, create_adapter
from app.core.models import AdapterRequest, AdapterResponse, ModelConfig
from app.reports.markdown import redact_text
from app.reports.schemas import ReportAnalysis, ReportFactPack, errored_analysis, skipped_analysis
from app.storage.model_store import ModelStore

_SYSTEM_PROMPT = """你是大模型 API 网关上线前评测报告分析助手。
请基于输入的结构化评测事实包，生成中文分析 JSON。
不要判断模型是否允许上线，只说明观测结果、风险点和建议下一步。
如果数据不足，请明确说明需要补测，不要编造。
输出必须是 JSON，不要包裹 Markdown 代码块。
不要输出 API key、密钥或完整原始报文。
"""

def extract_json_object(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start, end = stripped.find("{"), stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start:end + 1]
    raise ValueError("analysis output does not contain a JSON object")

class ReportAnalyzer:
    def __init__(self, model_store: ModelStore | None = None, adapter_factory: Callable[[ModelConfig], BaseAdapter] | None = None):
        self.model_store = model_store or ModelStore()
        self.adapter_factory = adapter_factory or create_adapter

    async def analyze(self, facts: ReportFactPack) -> ReportAnalysis:
        analysis_model_id = self.model_store.get_analysis_model_id()
        if not analysis_model_id:
            return skipped_analysis("未配置报告分析模型 analysis_model_id")
        model = self.model_store.get(analysis_model_id)
        if model is None:
            return errored_analysis(f"报告分析模型不存在：{analysis_model_id}", analysis_model_id=analysis_model_id)
        adapter = self.adapter_factory(model)
        prompt = redact_text(json.dumps(facts.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str))
        response = await adapter.complete(AdapterRequest(prompt=prompt, system_prompt=_SYSTEM_PROMPT, max_tokens=2048, temperature=0))
        if not response.ok:
            return errored_analysis("报告分析模型请求失败", analysis_model_id=analysis_model_id, raw_excerpt=redact_text(str(response.error or response.raw or response.content)[:1000]))
        try:
            payload = json.loads(extract_json_object(response.content))
            payload["analysis_model_id"] = analysis_model_id
            payload["analysis_status"] = "completed"
            return ReportAnalysis.model_validate(payload)
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            return errored_analysis(f"报告分析模型输出 JSON 解析失败：{exc}", analysis_model_id=analysis_model_id, raw_excerpt=redact_text(response.content[:1000]))
```

- [ ] **Step 4: Verify Task 3**

Run:

```powershell
uv run pytest tests\test_report_analyzer.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add app\reports\analyzer.py tests\test_report_analyzer.py
git commit -m "feat: 调用固定模型生成报告分析"
```

---

### Task 4: Integrate analysis into runner and persisted task result

**Files:**
- Modify: `D:\lakala\LLM_Benchmark\app\core\models.py`
- Modify: `D:\lakala\LLM_Benchmark\app\core\runner.py`
- Modify: `D:\lakala\LLM_Benchmark\tests\test_runner_fake_upstream.py`

- [ ] **Step 1: Write failing runner tests**

Add tests proving: configured analysis model persists completed analysis; analysis adapter failure keeps `result.status == "completed"` and sets `result.analysis["analysis_status"] == "error"`.

Use fake adapters that branch on `self.config.id == "report-analyzer"` and otherwise call existing `FakeAdapter`.

- [ ] **Step 2: Verify failing test**

Run:

```powershell
uv run pytest tests\test_runner_fake_upstream.py -q
```

Expected: fails because `TaskResult.analysis` and `write_markdown_report(result, self.reports_dir, facts=facts, analysis=analysis)` are missing.

- [ ] **Step 3: Extend `TaskResult`**

In `app/core/models.py`, add below `report_path`:

```python
    analysis_model_id: str | None = None
    analysis: dict[str, Any] | None = None
```

- [ ] **Step 4: Update runner finalization**

In `app/core/runner.py`, import:

```python
from app.reports.analyzer import ReportAnalyzer
from app.reports.facts import build_report_fact_pack
```

Replace final report block with:

```python
        result.results = metric_results
        result.finished_at = utc_now()
        result.duration_ms = elapsed_ms(start)
        facts = build_report_fact_pack(result)
        analysis = await ReportAnalyzer(model_store=self.model_store, adapter_factory=self.adapter_factory).analyze(facts)
        result.analysis_model_id = analysis.analysis_model_id
        result.analysis = analysis.model_dump(mode="json")
        report_path = write_markdown_report(result, self.reports_dir, facts=facts, analysis=analysis)
        result.report_path = str(report_path)
        self.task_store.save(result)
        return result
```

- [ ] **Step 5: Hold commit until Task 5**

Do not commit if tests fail only because Markdown signature is not updated. Commit together with Task 5 after green.

---

### Task 5: Rewrite Markdown report as dashboard + details

**Files:**
- Modify: `D:\lakala\LLM_Benchmark\app\reports\markdown.py`
- Modify: `D:\lakala\LLM_Benchmark\tests\test_report_localization.py`
- Modify: `D:\lakala\LLM_Benchmark\tests\test_runner_fake_upstream.py`

- [ ] **Step 1: Update Markdown tests**

Update report tests to pass `facts=build_report_fact_pack(result)` and this complete analysis object:

```python
analysis = ReportAnalysis(
    analysis_status="completed",
    analysis_model_id="report-analyzer",
    executive_summary="整体连通性正常，但仍需关注上下文和并发稳定性。",
    key_findings=["连通性指标完成", "错误处理指标完成"],
    risk_notes=["上下文能力需要结合明细继续确认"],
    metric_notes=[],
    recommended_next_steps=["复核异常指标的原始错误"],
)
```

Assert these strings exist:

```python
assert "## 0. LLM 分析摘要" in text
assert "## 2. 指标仪表盘" in text
assert "| 指标总数 | 已完成 | 异常 | 已跳过 |" in text
assert "## 3. 指标总表" in text
assert "| 指标 | 状态 | 核心观测 | 建议关注 |" in text
assert "## 4. 指标明细" in text
assert "## 5. 附录" in text
```

Add a redaction test with observation/error text containing values built as `"sk-" + "secret-123456"` and `"ark-" + "abcdef-123456"`; assert neither raw value appears and `sk-***` / `ark-***` do appear.

- [ ] **Step 2: Verify failing tests**

Run:

```powershell
uv run pytest tests\test_report_localization.py tests\test_runner_fake_upstream.py -q
```

Expected: fails because current Markdown writer has old signature/layout.

- [ ] **Step 3: Extend redaction and imports**

In `app/reports/markdown.py`, support both key styles:

```python
_SECRET_PATTERNS = [re.compile(r"sk-[A-Za-z0-9._-]+"), re.compile(r"ark-[A-Za-z0-9._-]+")]

def redact_text(text: str) -> str:
    redacted = text
    redacted = _SECRET_PATTERNS[0].sub("sk-***", redacted)
    redacted = _SECRET_PATTERNS[1].sub("ark-***", redacted)
    return redacted
```

Import:

```python
from app.reports.facts import build_report_fact_pack
from app.reports.schemas import ReportAnalysis, ReportFactPack, skipped_analysis
```

- [ ] **Step 4: Change report writer signature**

Use:

```python
def write_markdown_report(result: TaskResult, reports_dir: Path, facts: ReportFactPack | None = None, analysis: ReportAnalysis | None = None) -> Path:
    facts = facts or build_report_fact_pack(result)
    analysis = analysis or skipped_analysis("未执行 LLM 报告分析")
```

- [ ] **Step 5: Render sections in exact order**

Inside `write_markdown_report`, build these sections:

```text
# 大模型 API 评测报告 - task_id
## 0. LLM 分析摘要
## 1. 任务概览
## 2. 指标仪表盘
## 3. 指标总表
## 4. 指标明细
## 5. 附录
```

Use `facts.status_counts` for dashboard counts. Use `facts.metric_facts` for `核心观测` and `建议关注`. Preserve full `item.observations` and `item.errors` JSON blocks in details. Render appendices with `facts.model_dump(mode="json")` and `analysis.model_dump(mode="json")`.

- [ ] **Step 6: Verify Task 4 and Task 5 together**

Run:

```powershell
uv run pytest tests\test_report_localization.py tests\test_runner_fake_upstream.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Tasks 4 and 5**

```powershell
git add app\core\models.py app\core\runner.py app\reports\markdown.py tests\test_report_localization.py tests\test_runner_fake_upstream.py
git commit -m "feat: 生成仪表盘式LLM分析报告"
```

---

### Task 6: README and full verification

**Files:**
- Modify: `D:\lakala\LLM_Benchmark\README.md`

- [ ] **Step 1: Document analysis model config**

Add to README:

```markdown
### 报告分析模型

报告生成阶段可以使用固定的分析模型，对结构化评测事实包生成中文分析摘要。分析模型配置在 `data/models.json` 顶层：

```json
{
  "analysis_model_id": "report-analyzer",
  "models": [
    {
      "id": "report-analyzer",
      "name": "报告分析模型",
      "protocol": "chat_completions",
      "base_url": "https://analysis.example.com/v1",
      "api_key": "sk-redacted",
      "model": "report-analysis-model"
    }
  ]
}
```

如果未配置 `analysis_model_id`，或分析模型调用失败，基础评测任务仍会完成；Markdown 报告会显示分析跳过或失败原因。
```

- [ ] **Step 2: Run full tests**

Run:

```powershell
uv run pytest -q
```

Expected: all tests pass. The existing FastAPI/TestClient Starlette deprecation warning may remain.

- [ ] **Step 3: Inspect ignored runtime files**

Run:

```powershell
git status --short --ignored
```

Expected runtime paths remain ignored: `data/`, `reports/`, `.venv/`, `.pytest_cache/`, `.superpowers/`.

- [ ] **Step 4: Scan staged changes for secrets before commit**

Run:

```powershell
git diff --cached | Select-String -Pattern 'sk-[A-Za-z0-9._-]{10,}|ark-[A-Za-z0-9._-]{10,}'
```

Expected: no real secrets. `sk-redacted` is acceptable.

- [ ] **Step 5: Commit README**

```powershell
git add README.md
git commit -m "docs: 说明报告分析模型配置"
```

---

## Self-Review Checklist

- Spec coverage: tasks cover `analysis_model_id`, legacy storage, fact pack, fixed analyzer, JSON parsing, dashboard report, failure isolation, redaction, tests, and README.
- Placeholder scan: no task relies on an undefined file, type, command, or vague future action.
- Type consistency: `ReportFactPack`, `ReportAnalysis`, `TaskResult.analysis`, `TaskResult.analysis_model_id`, and `write_markdown_report(result, reports_dir, facts=facts, analysis=analysis)` are introduced before or alongside their use.
- Security: plan preserves ignored runtime data and scans for `sk-` / `ark-` secrets before commits.
