from __future__ import annotations

from app.core.models import MetricInfo, PlanInfo

GATEWAY_BASELINE_V1_METRICS = [
    "connectivity",
    "latency_breakdown",
    "context_length",
    "output_length",
    "concurrency",
    "rate_limit",
    "error_handling",
    "token_usage_accuracy",
    "stream_spec",
]

_METRIC_NAMES = {
    "connectivity": "连通性",
    "latency_breakdown": "延迟拆解",
    "context_length": "上下文长度",
    "output_length": "输出长度",
    "concurrency": "并发承载",
    "rate_limit": "限流行为",
    "error_handling": "错误处理",
    "token_usage_accuracy": "Token 用量观测（Usage）",
    "stream_spec": "流式规范性",
}

_METRIC_DESCRIPTIONS = {
    "connectivity": "检查模型接口是否可访问、响应是否为可解析 JSON、是否返回有效内容、finish_reason 和 usage 等基础字段。",
    "latency_breakdown": "采集流式调用的首包/首 token 延迟（TTFT）、端到端耗时、流式输出时长、估算吞吐等性能观测。",
    "context_length": "按配置的上下文长度分档构造长上下文请求，检查模型是否能找回指定 marker，用于观察当前网关链路的可用上下文能力。",
    "output_length": "按配置的最大输出 token 发起长输出请求，观察实际输出长度、finish_reason 和 usage 中的 completion_tokens。",
    "concurrency": "按配置的并发档位发起请求，统计成功、失败、延迟分布等，用于观察当前模型通道的并发承载情况。",
    "rate_limit": "基于并发探测结果观察是否出现 429 或其他明确限流信号，并记录首次触发限流的并发档位。",
    "error_handling": "构造无效 key、无效模型、空输入、非法参数、上下文超限等异常场景，检查网关错误结构是否稳定清晰。",
    "token_usage_accuracy": "观察响应中的 usage token 字段，并与本地启发式估算值做辅助对比；该项不作为自动通过/失败判定。",
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
        priority="P1" if metric_id == "stream_spec" else "P0",
        name=get_metric_name(metric_id),
        description=get_metric_description(metric_id),
        default_in_gateway_baseline_v1=True,
    )
    for metric_id in GATEWAY_BASELINE_V1_METRICS
}

PLANS: dict[str, PlanInfo] = {
    "gateway_baseline_v1": PlanInfo(
        id="gateway_baseline_v1",
        name="模型网关基础工程评测 V1",
        description="默认基础评测计划：覆盖连通性、延迟、上下文、输出、并发、限流、错误处理、Token 用量和流式规范性。",
        metric_ids=GATEWAY_BASELINE_V1_METRICS,
    )
}
