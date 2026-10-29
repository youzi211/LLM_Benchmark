import assert from "node:assert/strict";
import test from "node:test";

import { createSingleFlight } from "../src/utils/singleFlight.ts";

test("concurrent callers share one in-flight request", async () => {
  let calls = 0;
  let resolveRequest: ((value: string) => void) | undefined;
  const request = createSingleFlight(() => {
    calls++;
    return new Promise<string>((resolve) => {
      resolveRequest = resolve;
    });
  });

  const first = request();
  const second = request();
  assert.equal(calls, 1);

  resolveRequest?.("ok");
  assert.deepEqual(await Promise.all([first, second]), ["ok", "ok"]);
});

test("a settled request allows a later refresh", async () => {
  let calls = 0;
  const request = createSingleFlight(async () => {
    calls++;
    return calls;
  });

  assert.equal(await request(), 1);
  assert.equal(await request(), 2);
  assert.equal(calls, 2);
});

test("a rejected request does not poison later calls", async () => {
  let calls = 0;
  const request = createSingleFlight(async () => {
    calls++;
    if (calls === 1) throw new Error("boom");
    return "ok";
  });

  await assert.rejects(request(), /boom/);
  assert.equal(await request(), "ok");
});
