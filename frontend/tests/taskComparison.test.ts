import assert from "node:assert/strict";
import test from "node:test";

import { comparisonCsv, comparisonMetrics } from "../src/utils/taskComparison.ts";

test("CSV exports the same metric matrix and escapes quoted values", () => {
  const csv = comparisonCsv([
    { id: 'a"1', type: "basic", task: { task_id: "a", results: [{ metric_id: "x", metric_name: "指标", summary: '值,"一"', status: "completed" }] } },
    { id: "b", type: "basic", task: { task_id: "b", results: [] } },
  ]);
  assert.equal(csv, '"指标","a""1","b"\n"指标","值,""一""","—"');
});

test("stress tasks expose throughput and request reliability in task comparison", () => {
  const metrics = comparisonMetrics("stress", {
    task_id: "stress-a",
    status: "completed",
    normalized_result: {
      status: "completed",
      summary: {
        best_req_throughput: 12.5,
        best_output_throughput: 800,
      },
      runs: [
        { total: 10, success: 9, failed: 1, p95_latency_seconds: 1.8 },
        { total: 10, success: 8, failed: 2, p95_latency_seconds: 2.4 },
      ],
    },
  });

  assert.deepEqual(
    metrics.map((metric) => [metric.key, metric.summary]),
    [
      ["stress:req_throughput", "12.5 req/s"],
      ["stress:output_throughput", "800 tok/s"],
      ["stress:success_rate", "85.0% (17/20)"],
      ["stress:p95_latency", "2.4 s"],
      ["stress:runs", "2"],
    ],
  );
});

test("intelligence tasks expose dataset scores and their average", () => {
  const metrics = comparisonMetrics("intelligence", {
    task_id: "intel-a",
    status: "completed",
    normalized_result: {
      status: "completed",
      dataset_results: [
        { dataset: "bbh", pretty_name: "BBH", score: 80 },
        { dataset: "gsm8k", pretty_name: "GSM8K", score: 70 },
      ],
    },
  });

  assert.deepEqual(
    metrics.map((metric) => [metric.key, metric.summary]),
    [
      ["intelligence:average_score", "75.0"],
      ["intelligence:bbh", "80.0"],
      ["intelligence:gsm8k", "70.0"],
    ],
  );
});
