import assert from "node:assert/strict";
import test from "node:test";
import { taskErrorSummary } from "../src/utils/taskError.ts";

test("task and nested suite errors produce readable summaries", () => {
  assert.equal(taskErrorSummary({ status: "completed", error: "old error" }), "");
  assert.equal(taskErrorSummary({ status: "failed", error: { message: "连接超时" } }), "连接超时");
  assert.equal(taskErrorSummary({ status: "partial", errors: [{ step: "stress", message: { message: "服务不可达" } }] }), "服务不可达");
  assert.match(taskErrorSummary({ status: "interrupted" }), /未提供原因/);
});
test("summaries redact before truncating and do not dump arbitrary objects", () => {
  const result = taskErrorSummary({ status: "failed", error: "Bearer dummy-token sk-dummy-test-key api_key=dummy-value " + "长".repeat(100) });
  assert.ok(Array.from(result).length <= 60);
  assert.doesNotMatch(result, /dummy/);
  assert.match(taskErrorSummary({ status: "failed", error: { api_key: "dummy" } }), /未提供原因/);
  assert.doesNotMatch(taskErrorSummary({ status: "failed", error: 'upstream {"api_key":"dummy-key"} password=dummy-password' }), /dummy/);
});
