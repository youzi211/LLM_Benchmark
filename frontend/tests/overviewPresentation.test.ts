import assert from "node:assert/strict";
import test from "node:test";
import { formatDurationMetric } from "../src/overview/presentation.ts";

test("missing and invalid durations stay unavailable instead of becoming zero", () => {
  for (const value of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, -1]) {
    assert.deepEqual(formatDurationMetric(value), { value: "—", unit: "" });
  }
});

test("zero and sub-second durations use milliseconds", () => {
  assert.deepEqual(formatDurationMetric(0), { value: "0", unit: "毫秒" });
  assert.deepEqual(formatDurationMetric(245.4), { value: "245", unit: "毫秒" });
  assert.deepEqual(formatDurationMetric(999), { value: "999", unit: "毫秒" });
});

test("long durations have compact units without changing the source metric", () => {
  assert.deepEqual(formatDurationMetric(1000), { value: "1", unit: "秒" });
  assert.deepEqual(formatDurationMetric(35600), { value: "35.6", unit: "秒" });
  assert.deepEqual(formatDurationMetric(60000), { value: "1", unit: "分钟" });
  assert.deepEqual(formatDurationMetric(125000), { value: "2.1", unit: "分钟" });
  assert.deepEqual(formatDurationMetric(3600000), { value: "1", unit: "小时" });
  assert.deepEqual(formatDurationMetric(9000000), { value: "2.5", unit: "小时" });
});
