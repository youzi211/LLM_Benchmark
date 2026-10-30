import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTaskCenterItems,
  filterTaskCenterItems,
  taskDetailLocation,
  taskIdFromQuery,
} from "../src/utils/taskCenter.ts";

test("task center merges lanes and orders tasks by latest activity", () => {
  const items = buildTaskCenterItems({
    basic: [
      {
        task_id: "basic-old",
        status: "completed",
        model_id: "model-a",
        finished_at: "2026-10-28T10:00:00Z",
        duration_ms: 900,
      },
    ],
    stress: [
      {
        task_id: "stress-new",
        status: "running",
        model_id: "model-b",
        updated_at: "2026-10-29T11:00:00Z",
      },
    ],
    intelligence: [
      {
        task_id: "intel-middle",
        status: "completed",
        model_id: "model-c",
        completed_at: "2026-10-29T09:00:00Z",
      },
    ],
  });

  assert.deepEqual(
    items.map((item) => [item.id, item.lane, item.model]),
    [
      ["stress-new", "stress", "model-b"],
      ["intel-middle", "intelligence", "model-c"],
      ["basic-old", "basic", "model-a"],
    ],
  );
});

test("task center filters queued and running tasks as active", () => {
  const items = buildTaskCenterItems({
    basic: [
      { task_id: "basic-queued", status: "queued", model_id: "model-a" },
      { task_id: "basic-done", status: "completed", model_id: "model-a" },
    ],
    stress: [
      { task_id: "stress-running", status: "running", model_id: "model-b" },
      { task_id: "stress-error", status: "failed", model_id: "model-b" },
    ],
    intelligence: null,
  });

  assert.deepEqual(
    filterTaskCenterItems(items, {
      lane: "all",
      status: "active",
      query: "",
    }).map((item) => item.id).sort(),
    ["basic-queued", "stress-running"],
  );
  assert.deepEqual(
    filterTaskCenterItems(items, {
      lane: "stress",
      status: "attention",
      query: "model-b",
    }).map((item) => item.id),
    ["stress-error"],
  );
});

test("each task lane deep-links to its existing detail page", () => {
  assert.deepEqual(taskDetailLocation("basic", "task_1"), {
    path: "/basic",
    query: { task_id: "task_1" },
  });
  assert.deepEqual(taskDetailLocation("stress", "stress_1"), {
    path: "/stress",
    query: { task_id: "stress_1" },
  });
  assert.deepEqual(taskDetailLocation("intelligence", "intel_1"), {
    path: "/intelligence",
    query: { task_id: "intel_1" },
  });
});

test("task detail links accept a single query id or the first repeated id", () => {
  assert.equal(taskIdFromQuery("task_1"), "task_1");
  assert.equal(taskIdFromQuery(["task_2", "task_3"]), "task_2");
  assert.equal(taskIdFromQuery(""), null);
  assert.equal(taskIdFromQuery(undefined), null);
});
