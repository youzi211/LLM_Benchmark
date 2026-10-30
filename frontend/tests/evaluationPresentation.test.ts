import assert from "node:assert/strict";
import test from "node:test";
import { effectiveDatasetNames, formatEvaluationDuration, metricResultCounts, progressPercentOf, scorePercent } from "../src/evaluation/presentation.ts";

test("duration formatting preserves a real zero and keeps missing values unavailable", () => {
  assert.equal(formatEvaluationDuration(0), "0 毫秒");
  assert.equal(formatEvaluationDuration(125000), "2.1 分钟");
  assert.equal(formatEvaluationDuration(9000000), "2.5 小时");
  assert.equal(formatEvaluationDuration("2500"), "2.5 秒");
  for (const value of [null, undefined, "", "  ", false, {}, [], -1, Infinity]) {
    assert.equal(formatEvaluationDuration(value), "—");
  }
});

test("progress prefers overall percent, including an explicit zero", () => {
  assert.equal(progressPercentOf({ overall_percent: 0, percent: 45 }), 0);
  assert.equal(progressPercentOf({ percent: 42.5 }), 42.5);
  assert.equal(progressPercentOf({ overall_percent: null, percent: 65 }), 65);
  assert.equal(progressPercentOf({ percent: 120 }), 100);
});

test("unknown and invalid progress is not displayed as zero percent", () => {
  for (const value of [null, undefined, {}, { percent: null }, { percent: "" }, { percent: -1 }, { percent: false }]) {
    assert.equal(progressPercentOf(value), undefined);
  }
});

test("fractional and percentage scores share a readable percentage scale", () => {
  assert.equal(scorePercent(0), 0);
  assert.equal(scorePercent(0.8764), 87.6);
  assert.equal(scorePercent(1), 100);
  assert.equal(scorePercent(87.64), 87.6);
});

test("unscored datasets and negative sentinels do not become zero scores", () => {
  for (const value of [null, undefined, "", "  ", false, [], {}, -1, -1000, NaN, Infinity]) {
    assert.equal(scorePercent(value), null);
  }
});

test("metric counts describe execution statuses rather than launch eligibility", () => {
  assert.deepEqual(metricResultCounts([
    { status: "completed" }, { status: "completed" }, { status: "error" }, { status: "skipped" },
  ]), { completed: 2, errors: 1, skipped: 1, total: 4 });
  assert.deepEqual(metricResultCounts(undefined), { completed: 0, errors: 0, skipped: 0, total: 0 });
});

test("default dataset previews follow the local/default intersection used by custom requests", () => {
  assert.deepEqual(effectiveDatasetNames(["gsm8k", "bbh"], ["gsm8k", "mbpp"], false, []), ["gsm8k"]);
  assert.deepEqual(effectiveDatasetNames(["bbh"], ["gsm8k"], false, []), ["bbh"]);
});

test("custom dataset choices are local and keep the existing empty-selection fallback", () => {
  assert.deepEqual(effectiveDatasetNames(["gsm8k", "bbh"], [], true, ["bbh", "bbh", "unavailable"]), ["bbh"]);
  assert.deepEqual(effectiveDatasetNames(["gsm8k", "bbh"], [], true, []), ["gsm8k", "bbh"]);
  assert.deepEqual(effectiveDatasetNames([], [], true, []), []);
});
