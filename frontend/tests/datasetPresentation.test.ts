import assert from "node:assert/strict";
import test from "node:test";

import { datasetSummary } from "../src/utils/datasetPresentation.ts";

test("dataset summary folds names beyond the first two", () => {
  const summary = datasetSummary(["a", "b", "c", "d"], {
    a: { pretty_name: "数据集 A" },
    b: { pretty_name: "数据集 B" },
  });

  assert.equal(summary.short, "数据集 A、数据集 B +2");
  assert.equal(summary.full, "数据集 A、数据集 B、c、d");
});

test("dataset summary falls back to the raw id when pretty_name is missing", () => {
  assert.equal(datasetSummary(["swe_bench_v2", "gsm8k"], { gsm8k: { pretty_name: "数学题" } }).short, "swe_bench_v2、数学题");
});

test("dataset summary shows a dash for missing or blank datasets", () => {
  assert.deepEqual(datasetSummary(undefined), { short: "—", full: "" });
  assert.deepEqual(datasetSummary([]), { short: "—", full: "" });
  assert.deepEqual(datasetSummary(["", "  "]), { short: "—", full: "" });
});
