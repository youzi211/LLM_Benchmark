import assert from "node:assert/strict";
import test from "node:test";

import {
  buildStressGroups,
  formatStressLoad,
  stressMetricValue,
  stressRatePercent,
  stressStatusLabel,
} from "../src/stress/stressView.ts";

test("closed-loop runs show real concurrency when rate is unlimited", () => {
  assert.deepEqual(formatStressLoad(
    { parallel: 140, rate: -1 },
    { open_loop: false },
  ), {
    label: "并发 140",
    axisLabel: "P140",
    kind: "parallel",
  });
});

test("open-loop runs show request rate and explicit units", () => {
  assert.deepEqual(formatStressLoad(
    { parallel: -1, rate: 20 },
    { open_loop: true },
  ), {
    label: "速率 20 req/s",
    axisLabel: "20 req/s",
    kind: "rate",
  });

  assert.deepEqual(formatStressLoad(
    { parallel: -1, rate: -1 },
    { open_loop: true },
  ), {
    label: "不限速",
    axisLabel: "不限速",
    kind: "rate",
  });

  assert.deepEqual(formatStressLoad(
    { parallel: -1 },
    { open_loop: true },
  ), {
    label: "不限并发",
    axisLabel: "不限并发",
    kind: "parallel",
  });
});

test("historical runs without mode fall back to a valid positive load value", () => {
  assert.deepEqual(formatStressLoad(
    { parallel: 100, rate: -1 },
    {},
  ), {
    label: "并发 100",
    axisLabel: "P100",
    kind: "parallel",
  });

  assert.deepEqual(formatStressLoad(
    { parallel: -1, rate: 5 },
    {},
  ), {
    label: "速率 5 req/s",
    axisLabel: "5 req/s",
    kind: "rate",
  });

  assert.deepEqual(formatStressLoad(
    { parallel: -1, rate: -1 },
    {},
  ), {
    label: "—",
    axisLabel: "—",
    kind: "unknown",
  });
});

test("grouped stress tasks retain failed records and expose partial success", () => {
  const groups = buildStressGroups([
    {
      task_id: "stress-completed",
      model_id: "model-a",
      status: "completed",
      created_at: "2026-10-29T09:00:00Z",
      request_config: { dataset: "speed_benchmark", max_tokens: 512 },
      normalized_result: {
        runs: [{ parallel: 10, success_rate: 1, request_throughput: 4 }],
      },
    },
    {
      task_id: "stress-failed",
      model_id: "model-a",
      status: "failed",
      error: "upstream unavailable",
      created_at: "2026-10-29T09:05:00Z",
      request_config: { dataset: "speed_benchmark", max_tokens: 512 },
      normalized_result: null,
    },
    {
      task_id: "stress-interrupted",
      model_id: "model-a",
      status: "interrupted",
      created_at: "2026-10-29T09:10:00Z",
      request_config: { dataset: "speed_benchmark", max_tokens: 512 },
    },
  ]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].status, "partial");
  assert.equal(groups[0].group_count, 3);
  assert.equal(groups[0].normalized_result.runs.length, 1);
});

test("failed-only stress groups remain visible without runs", () => {
  const groups = buildStressGroups([{
    task_id: "stress-failed-only",
    model_id: "model-a",
    status: "failed",
    request_config: { open_loop: true, dataset: "speed_benchmark" },
    normalized_result: { runs: [] },
  }]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].status, "failed");
  assert.equal(groups[0].group_count, 1);
  assert.equal(groups[0].normalized_result.summary.best_req_throughput, null);
  assert.equal(groups[0].normalized_result.summary.best_output_throughput, null);
});

test("negative stress metric sentinels are treated as unavailable", () => {
  assert.equal(stressMetricValue(-1), undefined);
  assert.equal(stressMetricValue(-1000), undefined);
  assert.equal(stressMetricValue(null), undefined);
  assert.equal(stressMetricValue(undefined), undefined);
  assert.equal(stressMetricValue(""), undefined);
  assert.equal(stressMetricValue("  "), undefined);
  assert.equal(stressMetricValue(0), 0);
  assert.equal(stressMetricValue("12.5"), 12.5);
  assert.equal(stressMetricValue("not-a-number"), undefined);
});

test("missing success rates stay unavailable instead of becoming zero", () => {
  assert.equal(stressRatePercent(null), undefined);
  assert.equal(stressRatePercent(""), undefined);
  assert.equal(stressRatePercent(0), 0);
  assert.equal(stressRatePercent(0.5), 50);
  assert.equal(stressRatePercent(75), 75);
});

test("partial grouped stress results are labeled as partial failure", () => {
  assert.equal(stressStatusLabel("partial", true), "部分失败");
  assert.equal(stressStatusLabel("partial", false), "部分完成");
  assert.equal(stressStatusLabel("completed", true), "已完成");
});

test("open-loop tasks stay grouped across request-rate levels", () => {
  const groups = buildStressGroups([
    {
      task_id: "stress-rate-5",
      model_id: "model-a",
      status: "completed",
      request_config: {
        open_loop: true,
        dataset: "speed_benchmark",
        number: [100],
        rate: [5],
      },
      normalized_result: { runs: [{ rate: 5 }] },
    },
    {
      task_id: "stress-rate-20",
      model_id: "model-a",
      status: "completed",
      request_config: {
        open_loop: true,
        dataset: "speed_benchmark",
        number: [100],
        rate: [20],
      },
      normalized_result: { runs: [{ rate: 20 }] },
    },
  ]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].group_count, 2);
  assert.equal(groups[0].normalized_result.runs.length, 2);
  assert.match(groups[0].group_config, /开环速率/);
});

test("grouped durations remain unknown unless every member has a valid duration", () => {
  const task = { model_id: "model-a", status: "running", request_config: { dataset: "random" } };
  assert.equal(buildStressGroups([{ ...task, task_id: "unknown", duration_ms: null }])[0].duration_ms, null);
  assert.equal(buildStressGroups([{ ...task, task_id: "zero", duration_ms: 0 }])[0].duration_ms, 0);
  assert.equal(buildStressGroups([{ ...task, task_id: "known", duration_ms: 1500 }, { ...task, task_id: "unknown", duration_ms: null }])[0].duration_ms, null);
  assert.equal(buildStressGroups([{ ...task, task_id: "one", duration_ms: 1500 }, { ...task, task_id: "two", duration_ms: 500 }])[0].duration_ms, 2000);
});
