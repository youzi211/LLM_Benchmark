import assert from "node:assert/strict";
import test from "node:test";
import { schedulerHealth } from "../src/utils/serviceHealth.ts";

test("a scheduler explicitly disabled by configuration is neutral", () => {
  assert.deepEqual(schedulerHealth({ scheduler_disabled: true, scheduler: { ok: false, state: "disabled" } }), {
    state: "off", detail: "已按配置禁用",
  });
});

test("an enabled running scheduler stays healthy", () => {
  assert.deepEqual(schedulerHealth({ scheduler_disabled: false, scheduler: { ok: true, state: "running" } }), {
    state: "ok", detail: "单机定时调度器",
  });
});

test("unexpected scheduler failures stay visible with their actual state", () => {
  for (const state of ["stopped", "error", "disabled"]) {
    const result = schedulerHealth({ scheduler_disabled: false, scheduler: { ok: false, state } });
    assert.equal(result.state, "warn");
    assert.match(result.detail, new RegExp(state));
  }
});
