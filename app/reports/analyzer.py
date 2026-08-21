from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.adapters.base import AdapterFactory, create_adapter
from app.core.models import AdapterRequest
from app.reports.markdown import redact_text
from app.reports.schemas import (
    ReportAnalysis,
    ReportFactPack,
    errored_analysis,
    skipped_analysis,
)
from app.storage.model_store import ModelStore

_SYSTEM_PROMPT = """你是大模型 API 网关上线前评测报告分析助手。
请基于输入的结构化评测事实包，生成中文分析 JSON。
不要判断模型是否允许上线，只说明观测结果、风险点和建议下一步。
如果数据不足，请明确说明需要补测，不要编造。
输出必须是 JSON，不要包裹 Markdown 代码块。
不要输出 <think>、</think> 或任何推理过程。
不要输出 API key、密钥或完整原始报文。

必须使用以下 JSON 字段名：
{
  "one_sentence_summary": "一句话总结",
  "overall_assessment": "总体分析",
  "key_findings": ["关键发现"],
  "risks": ["风险点"],
  "recommended_next_steps": ["建议下一步"],
  "metric_notes": [
    {"metric_id": "指标 ID", "note": "分指标备注", "severity": "info|low|medium|high"}
  ]
}
"""


def _strip_think_blocks(text: str) -> str:
    """Remove model reasoning blocks before JSON extraction.

    Some reasoning models return ``<think>...</think>`` before the final
    answer. The think block may contain informal pseudo JSON such as
    ``{report_meta: ...}``, which should not be treated as the report JSON.
    """
    return re.sub(r"<think\b[^>]*>.*?</think>\s*", "", text, flags=re.IGNORECASE | re.DOTALL)


def extract_json_object(text: str) -> str:
    """Extract the first complete JSON object from text.

    Accepts:
    - Plain JSON object string.
    - Fenced ```json ... ``` block.
    - Surrounding prose: finds the first ``{`` and returns the first
      balanced object using brace counting with proper string handling.

    Raises ``ValueError`` when no JSON object exists.
    """
    if not isinstance(text, str):
        raise ValueError("input must be a string")

    stripped = _strip_think_blocks(text).strip()

    # Handle fenced ```json ... ``` block.
    if stripped.startswith("```"):
        # Drop the opening fence line.
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Drop the closing fence line if present.
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    if start == -1:
        raise ValueError("no JSON object found in text")

    depth = 0
    in_string = False
    escape = False

    for i, char in enumerate(stripped[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue

        if not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return stripped[start : i + 1]

    raise ValueError("no complete JSON object found in text")


class ReportAnalyzer:
    def __init__(
        self,
        model_store: ModelStore,
        adapter_factory: AdapterFactory | None = None,
    ):
        self.model_store = model_store
        self.adapter_factory = adapter_factory or create_adapter

    async def analyze(self, facts: ReportFactPack) -> ReportAnalysis:
        analysis_model_id = self.model_store.get_analysis_model_id()
        if analysis_model_id is None:
            return skipped_analysis("未配置报告分析模型 analysis_model_id")

        model_config = self.model_store.get(analysis_model_id)
        if model_config is None:
            return errored_analysis(
                f"报告分析模型不存在：{analysis_model_id}",
                analysis_model_id=analysis_model_id,
            )

        adapter = self.adapter_factory(model_config)

        fact_json = redact_text(
            json.dumps(facts.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        prompt = (
            "请基于以下评测事实包生成中文分析报告 JSON。\n\n"
            "事实包（已脱敏）：\n"
            f"{fact_json}\n\n"
            "请只输出合法 JSON，不要添加 Markdown 代码块或其他说明。"
        )

        request = AdapterRequest(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0,
        )

        try:
            response = await adapter.complete(request)
        except Exception as exc:
            return errored_analysis(
                f"调用报告分析模型异常：{redact_text(str(exc))}",
                analysis_model_id=analysis_model_id,
            )

        if not response.ok:
            raw_excerpt = redact_text(
                json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
            )
            return errored_analysis(
                "报告分析模型返回非成功响应。",
                analysis_model_id=analysis_model_id,
                raw_excerpt=raw_excerpt,
            )

        raw_content = redact_text(response.content)

        try:
            json_text = extract_json_object(raw_content)
            data = json.loads(json_text)
        except (ValueError, json.JSONDecodeError) as exc:
            return errored_analysis(
                f"报告分析模型返回内容解析失败：{exc}",
                analysis_model_id=analysis_model_id,
                raw_excerpt=raw_content,
            )

        if not isinstance(data, dict):
            return errored_analysis(
                "报告分析模型返回的 JSON 不是对象。",
                analysis_model_id=analysis_model_id,
                raw_excerpt=raw_content,
            )

        # Force the analysis metadata fields regardless of what the model produced.
        data["analysis_model_id"] = analysis_model_id
        data["analysis_status"] = "completed"

        try:
            analysis = ReportAnalysis.model_validate(data)
        except ValidationError as exc:
            return errored_analysis(
                f"报告分析结果校验失败：{exc}",
                analysis_model_id=analysis_model_id,
                raw_excerpt=raw_content,
            )

        return analysis

