import { test } from "node:test";
import assert from "node:assert/strict";
import { stressOption, abilityGroups } from "../src/utils/workspaceCharts.ts";

test("stress curves preserve missing points and zero throughput", () => {
  const option = stressOption([{ model_id: "a", metrics: [{ parallel: 1, output_throughput: 0 }, { parallel: 4, output_throughput: 20 }] },
    { model_id: "b", metrics: [{ parallel: 2, output_throughput: 15 }] }], "output_throughput", "tok/s", false);
  assert.deepEqual(option.series[0].data, [0, null, 20]);
  assert.equal(option.series[0].connectNulls, false);
});
test("capability charts keep distinct metrics apart and do not fill missing scores", () => {
  const groups = abilityGroups([{ model_id: "a", metrics: [{ dataset: "math", metric_id: "accuracy", score: .8, unit: "%", display_multiplier: 100 }] },
    { model_id: "b", metrics: [{ dataset: "math", metric_id: "latency", score: 2, unit: "s" }] }]);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].option.series[0].data, [80]);
  assert.deepEqual(groups[0].option.series[1].data, [null]);
});

test("legacy closed loop cannot leak into an open loop plot", () => {
  const option = stressOption([{ model_id: "legacy", metrics: [{ parallel: 1, rate: -1, output_throughput: 8 }] },
    { model_id: "open", load_mode: "open", metrics: [{ rate: 2, output_throughput: 12 }] }], "output_throughput", "tok/s", true);
  assert.deepEqual(option.xAxis.data, [2]);
  assert.equal(option.series.length, 1);
});
