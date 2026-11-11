import assert from "node:assert/strict";
import test from "node:test";
import { formatDate, timestamp } from "../src/utils/time.ts";

test("offsets describe the same instant and display in Beijing time", () => {
  assert.equal(formatDate("2026-11-10T14:55:50Z"), "2026/11/10 22:55:50 UTC+08:00");
  assert.equal(formatDate("2026-11-10T22:55:50+08:00"), formatDate("2026-11-10T14:55:50Z"));
  assert.equal(formatDate("2026-11-10T23:55:50Z"), "2026/11/11 07:55:50 UTC+08:00");
});
test("legacy wall times are never silently assigned a timezone", () => {
  assert.equal(timestamp("2026-08-24T17:39:02.265810"), undefined);
  assert.match(formatDate("2026-08-24T17:39:02.265810"), /时区未知/);
  assert.equal(formatDate(null), "—");
  assert.equal(timestamp("invalid"), undefined);
});
