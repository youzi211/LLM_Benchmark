import { test, expect } from "./fixtures";

test("model identity, default evidence and history navigation", async ({ page }) => {
  await page.goto("/#/models");
  await expect(page.getByRole("heading", { name: "模型工作台" })).toBeVisible();
  await expect(page.getByRole("link", { name: "同名测试模型", exact: true })).toHaveCount(2);
  await page.locator('a[href="#/models/ui-model"]').click();
  await expect(page.getByRole("heading", { name: "同名测试模型", exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("最新执行：失败", { exact: true })).toHaveCount(3);
  await page.getByRole("tab", { name: "能力评测", exact: true }).click();
  await expect(page.locator(".echart-box canvas")).toBeVisible();
  await expect(page.getByText("20", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "选择历史结果" }).click();
  await expect(page.getByRole("tab", { name: "评测历史" })).toHaveAttribute("aria-selected", "true");
});

test("professional comparison keeps condition differences visible", async ({ page }) => {
  await page.goto("/#/model-compare?ids=ui-model,ui-reference");
  await expect(page.getByText("执行条件存在差异")).toBeVisible();
  await expect(page.locator(".echart-box canvas")).toHaveCount(1);
  await page.getByRole("tab", { name: "性能压测", exact: true }).click();
  await expect(page.locator(".echart-box canvas")).toHaveCount(4);
  const sidebar = page.locator(".lb-desktop-sidebar");
  const before = await sidebar.boundingBox();
  await page.locator("#main-content").evaluate(el => el.scrollTo(0, el.scrollHeight));
  await expect.poll(() => page.locator("#main-content").evaluate(el => el.scrollTop)).toBeGreaterThan(100);
  expect((await sidebar.boundingBox())!.y).toBe(before!.y);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("Judge and sandbox configuration loads saved settings", async ({ page }) => {
  await page.goto("/#/settings/evaluation");
  await page.getByRole("button", { name: "配置 Judge LLM", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "评测环境配置" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("推理与 Judge 共享并发", { exact: false })).toBeVisible();
  await expect(drawer.getByText("ui-reference · DeepSeek · 对照模型", { exact: true }).first()).toBeVisible();
});

test("mobile model view has no document horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/#/models");
  await expect(page.getByRole("heading", { name: "模型工作台" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "展开导航" }).click();
  await expect(page.getByRole("dialog").getByRole("link", { name: "Judge LLM / 沙箱" })).toBeVisible();
});

test("empty model evidence never renders fabricated charts", async ({ page, api }) => {
  api.scenario = "empty";
  await page.goto("/#/models/ui-model");
  for (const tab of ["能力评测", "性能压测", "网关检查"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.getByText("暂无可展示结果", { exact: true })).toBeVisible();
    await expect(page.locator(".echart-box canvas")).toHaveCount(0);
  }
});

test("gateway comparison shows a matrix linked to task evidence", async ({ page }) => {
  await page.goto("/#/model-compare?ids=ui-model,ui-reference");
  await page.getByRole("tab", { name: "网关检查", exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "ui-model", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "ui-reference", exact: true })).toBeVisible();
  await expect(page.locator('.el-table__body a[href$="task_ui_completed"]')).toHaveCount(2);
  await expect(page.getByText("不支持，保留证据", { exact: true })).toHaveCount(2);
});

for (const lane of ["intelligence", "stress"]) {
  test(`${lane} cancellation stays pending until execution exits`, async ({ page, api }) => {
    api.cooperativeCancel = true;
    await page.goto(`/#/${lane}?task_id=${lane === 'intelligence' ? 'intel' : 'stress'}_ui_running`);
    await page.getByRole("button", { name: "取消任务", exact: true }).click();
    await page.locator(".el-message-box").getByRole("button", { name: /^(确定|确认|OK)$/ }).click();
    await expect(page.locator(".lb-eval-detail > header")).toContainText("取消中");
    await expect(page.getByText("已提交取消请求", { exact: true })).toBeVisible();
  });
}
