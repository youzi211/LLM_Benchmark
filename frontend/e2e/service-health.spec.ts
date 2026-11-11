import { test, expect } from "./fixtures";

test("configured disabled scheduler is neutral and Agent help stays dataset independent", async ({ page }, testInfo) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: {
    status: "ok", uptime_s: 7200, scheduler_disabled: true,
    models: { ok: true, count: 2 }, evalscope: { ok: true, state: "ready" },
    scheduler: { ok: false, state: "disabled" },
  } }));
  await page.route("**/api/overview/task-summary", (route) => route.fulfill({ json: {
    today_count: 0, final_count: 0, completed_count: 0, completion_rate: null, avg_duration_ms: null,
  } }));
  await page.goto("/#/intelligence");
  await expect(page.locator(".lb-conn-banner")).toHaveCount(0);
  await page.locator(".lb-page-hero").getByRole("button", { name: "新建能力评测", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新建能力评测", exact: true });
  await drawer.locator(".el-form-item").filter({ hasText: "执行方式" }).locator(".el-select__wrapper").click();
  await page.getByRole("option", { name: "OpenCode", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("请在 Agent 分类中选择本地可用的数据集");
  await expect(drawer.getByRole("alert")).not.toContainText(/SWE-bench|Pro V1|Terminal-Bench/);
  await page.screenshot({ path: testInfo.outputPath("agent-help.png"), animations: "disabled" });
  await page.goto("/#/overview");
  await expect(page.locator(".lb-sh__summary")).toHaveText("已启用服务 3/3 正常，另有 1 项未启用");
  const scheduler = page.locator(".lb-sh__item").filter({ hasText: "调度服务" });
  await expect(scheduler).toContainText("已按配置禁用");
  await expect(scheduler).toContainText("未启用");
  await expect(scheduler.getByRole("button", { name: "重试调度服务" })).toHaveCount(0);
  await expect(page.locator(".lb-conn-banner")).toHaveCount(0);
});

test("unexpected scheduler errors remain visible and retry refreshes health", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/health", (route) => {
    requests += 1;
    return route.fulfill({ json: {
      status: "ok", uptime_s: 7200, scheduler_disabled: false,
      models: { ok: true, count: 2 }, evalscope: { ok: true, state: "ready" },
      scheduler: { ok: false, state: "error" },
    } });
  });
  await page.goto("/#/intelligence");
  const scheduler = page.locator(".lb-conn-banner__svc").filter({ hasText: "调度" });
  await expect(scheduler).toHaveAttribute("title", "调度器状态：error");
  const before = requests;
  await scheduler.click();
  await expect.poll(() => requests).toBeGreaterThan(before);
});
