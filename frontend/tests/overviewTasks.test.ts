import assert from "node:assert/strict";
import test from "node:test";

import { buildOverviewTaskSummary } from "../src/overview/taskOverview.ts";

const now = new Date(2026, 9, 29, 12, 0, 0);

test("empty successful sources produce empty real-data states", () => {
  const summary = buildOverviewTaskSummary({
    basic: [],
    stress: [],
    intelligence: [],
  });

  assert.deepEqual(summary.runningTasks, []);
  assert.deepEqual(summary.recentTasks, []);
  assert.deepEqual(summary.failedLanes, []);
});

test("summary derives task KPIs and running tasks from real sources", () => {
  const summary = buildOverviewTaskSummary({
    basic: [{
      task_id: "task_completed",
      status: "completed",
      duration_ms: 1000,
      started_at: new Date(2026, 9, 29, 9, 0, 0).toISOString(),
      finished_at: new Date(2026, 9, 29, 9, 1, 0).toISOString(),
    }],
    stress: [
      {
        task_id: "task_failed",
        status: "failed",
        duration_ms: 3000,
        started_at: new Date(2026, 9, 29, 8, 0, 0).toISOString(),
        finished_at: new Date(2026, 9, 29, 8, 1, 0).toISOString(),
      },
      {
        task_id: "stress_task_running",
        model_id: "model-a",
        status: "running",
        started_at: new Date(2026, 9, 29, 11, 55, 0).toISOString(),
        progress_detail: { percent: 42 },
      },
    ],
    intelligence: [{
      task_id: "task_interrupted",
      status: "interrupted",
      started_at: new Date(2026, 9, 29, 10, 0, 0).toISOString(),
      finished_at: new Date(2026, 9, 29, 10, 1, 0).toISOString(),
    }],
  });

  assert.deepEqual(summary.runningTasks, [{
    id: "stress_task_running",
    type: "stress",
    model: "model-a",
    startedAt: new Date(2026, 9, 29, 11, 55, 0).getTime(),
    progress: 42,
    stage: "运行中",
  }]);
  assert.deepEqual(summary.recentTasks.map(({ lane, task }) => `${lane}:${task.task_id}`), [
    "intelligence:task_interrupted",
    "basic:task_completed",
    "stress:task_failed",
  ]);
});

test("a failed source is reported while successful lanes still render", () => {
  const summary = buildOverviewTaskSummary({
    basic: [{
      task_id: "task_completed",
      status: "completed",
      duration_ms: 1000,
      started_at: new Date(2026, 9, 29, 9, 0, 0).toISOString(),
    }],
    stress: null,
    intelligence: [],
  });

  assert.deepEqual(summary.failedLanes, ["stress"]);
  assert.deepEqual(summary.recentTasks.map(({ task }) => task.task_id), ["task_completed"]);
});
