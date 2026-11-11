import { test, expect } from "./fixtures";

test("legacy Mini results retain score and sample counts without a misleading category average", async ({ page }, testInfo) => {
  const task = {
    task_id: "mini-completed", model_id: "ui-model", status: "completed", datasets: ["mini"],
    progress_detail: { current_dataset: "mini", processed_count: null, total_count: null, overall_percent: 100,
      dataset_index: 1, dataset_total: 1, datasets: [{ dataset: "mini", processed_count: 1, total_count: 1 }] },
    normalized_result: { dataset_results: [{ dataset: "mini", pretty_name: "Mini", categories: ["Coding"], score: 1 }],
      category_summaries: [{ category: "Coding", dataset_count: 1, scored_dataset_count: 1, average_score: null }] },
  };
  await page.route("**/api/intelligence/tasks/mini-completed*", route => route.fulfill({ json: task }));
  await page.goto("/#/intelligence?task_id=mini-completed");
  await expect(page.getByText("已处理 1 / 1 样本", { exact: true })).toBeVisible();
  await expect(page.locator(".lb-intel-score")).toHaveText("100%");
  await page.getByRole("tab", { name: "能力维度", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "能力维度", exact: true }).getByText("Coding", { exact: true })).toBeVisible();
  await expect(page.getByText("未取得分数", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/不计算跨数据集平均分/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mini-category-results.png"), animations: "disabled" });
});

for (const [lane, reason, timeLabel] of [
  ["basic", "测试接口连接失败", "开始时间"],
  ["intelligence", "数据集执行失败", "创建时间"],
  ["stress", "部分档位执行失败", "创建时间"],
] as const) {
  test(`${lane} list explains failure and shows timestamp`, async ({ page, api }, testInfo) => {
    api.seedActive = false;
    await page.goto(`/#/${lane}`);
    const list = page.locator(".lb-eval-list");
    await expect(list.getByText(reason, { exact: true })).toBeVisible();
    await expect(list.locator("time").first()).toContainText(timeLabel);
    await expect(list.getByText(/2026\/10\/30 16:00:00 UTC\+08:00/).first()).toBeVisible();
    if (lane === "basic") await page.screenshot({ path: testInfo.outputPath("basic-trust.png"), animations: "disabled" });
  });
}

test("task center searches display names and retains unknown timezone", async ({ page }) => {
  await page.route("**/api/intelligence/tasks?*", route => route.fulfill({ json: [{
    task_id: "legacy-time", model_id: "ui-model", status: "failed",
    created_at: "2026-08-24T17:39:02.265810", error: { message: "历史任务错误" },
  }] }));
  await page.goto("/#/tasks");
  await page.getByPlaceholder("搜索任务 ID / 模型").fill("接入验证模型");
  await expect(page.getByText("历史任务错误", { exact: true })).toBeVisible();
  await expect(page.getByText(/2026-08-24.*时区未知/)).toBeVisible();
});

test("suite list shows configured model name and nested error", async ({ page }) => {
  await page.route("**/api/suites?*", route => route.fulfill({ json: [{
    suite_id: "suite-failed", model_id: "ui-model", status: "failed", updated_at: "2026-11-10T14:55:50Z",
    errors: [{ step: "intelligence", message: { message: "数据集读取失败" } }],
  }] }));
  await page.goto("/#/suites");
  const row = page.getByRole("row").filter({ hasText: "suite-failed" });
  await expect(row).toContainText("Qwen · 接入验证模型");
  await expect(row).toContainText("ui-model");
  await expect(row).toContainText("数据集读取失败");
});
