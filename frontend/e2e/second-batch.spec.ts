import { test, expect, lanes } from "./fixtures";

for (const lane of lanes) {
  test(`${lane.title} empty detail opens the existing configuration`, async ({ page, api }) => {
    await page.goto(`/#/${lane.lane}`);
    await page.locator(".lb-eval-detail").getByRole("button", { name: `新建${lane.title}`, exact: true }).click();
    await expect(page.getByRole("dialog", { name: `新建${lane.title}`, exact: true })).toBeVisible();
    expect(api.submissions).toHaveLength(0);
  });
}

test("model sorting sends a global sort request and explains comparison and evidence", async ({ page }, testInfo) => {
  const requests: URLSearchParams[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.pathname === "/api/model-evaluations") requests.push(url.searchParams);
  });
  await page.goto("/#/models");
  await expect(page.getByText("当前页成功证据泳道", { exact: true })).toBeVisible();
  await expect(page.locator("#compare-selection-hint")).toContainText("选择 2–4 个模型");
  await expect(page.getByRole("button", { name: "对比所选模型（0/4）" })).toBeDisabled();
  await expect(page.getByText(/已中断：执行未正常结束/)).toBeVisible();
  await expect(page.getByText(/最近成功证据：/)).toHaveCount(6);
  const sort = page.locator(".el-select").filter({ has: page.getByRole("combobox", { name: "模型排序" }) });
  await sort.click();
  await page.getByRole("option", { name: "覆盖度（高到低）", exact: true }).click();
  await expect.poll(() => requests.at(-1)?.get("sort_by")).toBe("coverage");
  expect(requests.at(-1)?.get("order")).toBe("desc");
  expect(requests.at(-1)?.get("page")).toBe("1");
  await sort.click();
  await page.getByRole("option", { name: "最后执行（新到旧）", exact: true }).click();
  await expect.poll(() => requests.at(-1)?.get("sort_by")).toBe("last_execution");
  await page.screenshot({ path: testInfo.outputPath("models-second-batch.png"), animations: "disabled" });
});

for (const count of [50, 51]) {
  test(`task center detects the real limit with ${count} records and paginates`, async ({ page }) => {
    await page.route("**/api/tasks?*", route => route.fulfill({ json: [] }));
    await page.route("**/api/intelligence/tasks?*", route => route.fulfill({ json: [] }));
    await page.route("**/api/stress/tasks?*", route => {
      expect(new URL(route.request().url()).searchParams.get("limit")).toBe("51");
      return route.fulfill({ json: Array.from({ length: count }, (_, index) => ({
        task_id: `limit-task-${String(index).padStart(2, "0")}`, status: "completed", model_id: "ui-model",
        created_at: new Date(Date.UTC(2026, 10, 11, 12, 59 - index)).toISOString(),
      })) });
    });
    await page.goto("/#/tasks");
    const tableRows = page.locator(".el-table__body-wrapper tbody tr");
    await expect(tableRows).toHaveCount(20);
    await expect(page.getByText(/已截断，仅显示各最近 50 条/)).toHaveCount(count === 51 ? 1 : 0);
    const pagination = page.getByLabel("任务列表分页");
    await pagination.getByRole("button", { name: /下一页/ }).click();
    await expect(tableRows.first()).toContainText("limit-task-20");
    await page.getByPlaceholder("搜索任务 ID / 模型").fill("limit-task-49");
    await expect(tableRows).toHaveCount(1);
    await expect(tableRows.first()).toContainText("limit-task-49");
    await expect(page.getByText("无匹配任务", { exact: true })).toHaveCount(0);
    await page.getByPlaceholder("搜索任务 ID / 模型").fill("no-matching-task");
    await expect(tableRows).toHaveCount(0);
    await expect(page.getByText("无匹配任务", { exact: true })).toBeVisible();
  });
}

test("theme buttons describe the actual next action and built-in labels use Chinese", async ({ page }) => {
  await page.goto("/#/models");
  await expect(page.getByRole("checkbox", { name: "选择所有行" })).toBeEnabled();
  await expect(page.getByText("共 2 条", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "设计系统", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "切换到暗色主题", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "切换到跟随系统主题", exact: true }).click();
  await page.getByRole("button", { name: "切换到亮色主题", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("intelligence list displays dataset names and a remaining count", async ({ page }) => {
  await page.route("**/api/intelligence/tasks?*", route => route.fulfill({ json: [{
    task_id: "dataset-list", model_id: "ui-model", status: "completed", datasets: ["gsm8k", "bbh", "extra_dataset"],
    created_at: "2026-11-11T08:00:00Z",
  }] }));
  await page.goto("/#/intelligence");
  const list = page.locator(".lb-eval-list");
  await expect(list).toContainText("GSM8K");
  await expect(list).toContainText("BBH");
  await expect(list).toContainText("+1");
});

test("suite empty action returns to the existing wizard without resetting fields", async ({ page, api }) => {
  await page.route("**/api/suites?*", route => route.fulfill({ json: [] }));
  await page.goto("/#/suites");
  const gateway = page.getByRole("checkbox", { name: "基础评测", exact: true });
  await page.locator(".panel-card .el-checkbox").filter({ hasText: "基础评测" }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "配置一键评测", exact: true }).click();
  await expect(gateway).toBeEnabled();
  await expect(gateway).not.toBeChecked();
  await expect(page.locator('[tabindex="-1"]').filter({ has: gateway })).toBeFocused();
  expect(api.submissions).toHaveLength(0);
});
