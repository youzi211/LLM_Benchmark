from __future__ import annotations

from app.core.models import MetricInfo, PlanInfo

# 自研指标只承担“模型网关接入验收 / 协议 smoke”职责。
# 正式模型能力评测和正式性能压测由 EvalScope 负责；这里保留少量
# 网关链路、协议兼容、错误结构、usage、长度与缓存信号检查。
GATEWAY_ACCEPTANCE_V1_METRICS = [
    "connectivity",
    "latency_breakdown",
    "context_length",
    "output_length",
    "error_handling",
    "token_usage_accuracy",
    "cache_behavior",
    "stream_spec",
]

# 兼容历史 metric_id：仍可通过 metric_ids 显式手动运行，但不再作为默认计划。
OPTIONAL_LEGACY_PERF_SMOKE_METRICS = [
    "concurrency",
    "rate_limit",
]

ALL_GATEWAY_METRICS = GATEWAY_ACCEPTANCE_V1_METRICS + OPTIONAL_LEGACY_PERF_SMOKE_METRICS

# 历史名称保留为别名，避免旧代码 import 断裂。
GATEWAY_BASELINE_V1_METRICS = GATEWAY_ACCEPTANCE_V1_METRICS

_METRIC_NAMES = {
    "connectivity": "连通性",
    "latency_breakdown": "延迟拆解",
    "context_length": "上下文长度",
    "output_length": "输出长度",
    "concurrency": "并发承载",
    "rate_limit": "限流行为",
    "error_handling": "错误处理",
    "token_usage_accuracy": "Token 用量观测（Usage）",
    "cache_behavior": "缓存能力（Prompt Cache）",
    "stream_spec": "流式规范性",
}

_METRIC_DESCRIPTIONS = {
    "connectivity": "检查模型接口是否可访问、响应是否为可解析 JSON、是否返回有效内容、finish_reason 和 usage 等基础字段。",
    "latency_breakdown": "采集一次轻量流式调用的首包/首 token 延迟（TTFT）和端到端耗时，仅作为网关链路 smoke；正式延迟、吞吐和分位数以 EvalScope 压测为准。",
    "context_length": "按配置的上下文长度分档构造长上下文请求，检查模型是否能找回指定 marker，用于观察当前网关链路的可用上下文能力。",
    "output_length": "按配置的最大输出 token 发起长输出请求，观察实际输出长度、finish_reason 和 usage 中的 completion_tokens。",
    "concurrency": "兼容保留的轻量并发 smoke 指标，可手动运行用于发现明显不可用；正式并发承载、吞吐和延迟分布以 EvalScope 压测为准。",
    "rate_limit": "兼容保留的轻量限流 smoke 指标，可手动观察 429 等信号；正式限流/容量边界以 EvalScope 压测结果为准。",
    "error_handling": "构造无效 key、无效模型、空输入、非法参数、上下文超限等异常场景，检查网关错误结构是否稳定清晰。",
    "token_usage_accuracy": "观察响应中的 usage token 字段，并与本地启发式估算值做辅助对比；该项不作为自动通过/失败判定。",
    "cache_behavior": "通过长稳定前缀的冷/热重复请求，观察缓存字段、缓存命中 token、总延迟变化等 Prompt Cache 行为；不做自动阈值判定。",
    "stream_spec": "检查流式接口是否符合 SSE 习惯格式，是否可解析、是否包含 [DONE]、finish_reason 和流式 usage 等字段。",
}


def get_metric_name(metric_id: str) -> str:
    return _METRIC_NAMES.get(metric_id, metric_id)


def get_metric_description(metric_id: str) -> str:
    return _METRIC_DESCRIPTIONS.get(metric_id, metric_id)


def format_metric_label(metric_id: str) -> str:
    name = get_metric_name(metric_id)
    return f"{name}（{metric_id}）" if name != metric_id else metric_id


METRICS: dict[str, MetricInfo] = {
    metric_id: MetricInfo(
        id=metric_id,
        priority=(
            "P2"
            if metric_id in OPTIONAL_LEGACY_PERF_SMOKE_METRICS
            else "P1"
            if metric_id in {"latency_breakdown", "context_length", "output_length", "cache_behavior", "stream_spec"}
            else "P0"
        ),
        name=get_metric_name(metric_id),
        description=get_metric_description(metric_id),
        default_in_gateway_baseline_v1=metric_id in GATEWAY_ACCEPTANCE_V1_METRICS,
    )
    for metric_id in ALL_GATEWAY_METRICS
}

PLANS: dict[str, PlanInfo] = {
    "gateway_acceptance_v1": PlanInfo(
        id="gateway_acceptance_v1",
        name="模型网关接入验收 V1",
        description="收缩后的默认自研指标计划：只做网关链路、协议兼容、错误结构、usage、长度与缓存 smoke；正式能力评测和正式性能压测交给 EvalScope。",
        metric_ids=GATEWAY_ACCEPTANCE_V1_METRICS,
    ),
    # 兼容旧调用方：gateway_baseline_v1 仍可用，但语义等同 gateway_acceptance_v1。
    "gateway_baseline_v1": PlanInfo(
        id="gateway_baseline_v1",
        name="模型网关接入验收 V1（兼容旧名）",
        description="兼容旧 plan_id；不再包含并发/限流正式压测，正式性能结果请使用 EvalScope stress。",
        metric_ids=GATEWAY_ACCEPTANCE_V1_METRICS,
    ),
}
