import assert from "node:assert/strict";
import test from "node:test";

import { shouldShowTaskListEmpty, taskById } from "../src/utils/taskListState.ts";

test("an empty task list is not shown while loading or after a list error", () => {
  assert.equal(shouldShowTaskListEmpty(true, "", 0), false);
  assert.equal(shouldShowTaskListEmpty(false, "network error", 0), false);
  assert.equal(shouldShowTaskListEmpty(false, "", 0), true);
  assert.equal(shouldShowTaskListEmpty(false, "", 1), false);
});

test("a failed detail request falls back to the newly selected cached task", () => {
  const tasks = [{ task_id: "task-a" }, { task_id: "task-b", status: "failed" }];

  assert.deepEqual(taskById(tasks, "task-b"), tasks[1]);
  assert.equal(taskById(tasks, "missing"), null);
});
