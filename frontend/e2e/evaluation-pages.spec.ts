import { test, expect, lanes } from "./fixtures";

for (const definition of lanes) {
  const { lane, title, completed, running } = definition;

  test(`${title}：默认提交与配置抽屉`, async ({ page, api }) => {
    api.seedActive = false;
    await page.goto(`/#/${lane}`);
    await page.getByRole("button", { name: `新建${title}`, exact: true }).click();
    const drawer = page.getByRole("dialog", { name: `新建${title}`, exact: true });
    await expect(drawer.getByText("Qwen · 接入验证模型", { exact: true })).toBeVisible();
    await drawer.getByRole("button", { name: `开始${title}`, exact: true }).click();
    await expect(drawer).toBeHidden();
    await expect.poll(() => api.submissions.length).toBe(1);
    expect(api.submissions[0]).toEqual({ path: definition.submit, body: lane === "basic" ? { model_id: "ui-model", plan_id: "gateway_acceptance_v1" } : { model_id: "ui-model" } });
    await expect(page.locator(".lb-eval-task-title")).toContainText(`${lane}_ui_created_1`);
  });

  test(`${title}：选择、清空与任务对比`, async ({ page, api }) => {
    api.seedActive = false;
    await page.goto(`/#/${lane}`);
    const list = page.locator(".lb-eval-list");
    if (lane === "stress") await list.getByRole("switch", { name: "按方案归组" }).press("Space");
    const checkboxes = list.locator(".el-table__body-wrapper .el-checkbox");
    await expect(checkboxes).toHaveCount(2);
    await checkboxes.nth(0).click();
    await expect(list.getByRole("button", { name: "对比任务", exact: true })).toBeDisabled();
    await checkboxes.nth(1).click();
    await list.getByRole("button", { name: "取消选择", exact: true }).click();
    await expect(list.locator(".lb-eval-bulk")).toBeHidden();
    await expect(list.locator(".el-table__body-wrapper .el-checkbox.is-checked")).toHaveCount(0);
    await checkboxes.nth(0).click();
    await checkboxes.nth(1).click();
    await list.getByRole("button", { name: "对比任务", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`#/compare\\?.*types=${lane}`));
    expect(new URLSearchParams(new URL(page.url()).hash.split("?")[1]).get("types")).toBe(`${lane},${lane}`);
  });

  test(`${title}：批量重跑保留任务参数`, async ({ page, api }) => {
    api.seedActive = false;
    await page.goto(`/#/${lane}`);
    const list = page.locator(".lb-eval-list");
    if (lane === "stress") await list.getByRole("switch", { name: "按方案归组" }).press("Space");
    await list.locator(".el-table__body-wrapper .el-checkbox").nth(0).click();
    await list.locator(".el-table__body-wrapper .el-checkbox").nth(1).click();
    await list.getByRole("button", { name: "重新运行", exact: true }).click();
    await expect.poll(() => api.submissions.length).toBe(2);
    expect(api.submissions.every((item) => item.body.model_id === "ui-model")).toBe(true);
    if (lane === "basic") expect(api.submissions[0].body.metric_ids).toEqual(["connectivity", "stream_spec", "cache_behavior"]);
    if (lane === "stress") expect(api.submissions[0].body.dataset).toBe("longalpaca");
    if (lane === "intelligence") expect(api.submissions[0].body.datasets).toEqual(["gsm8k", "bbh"]);
    await expect(list.locator(".lb-eval-bulk")).toBeHidden();
  });

  test(`${title}：运行中任务可取消，未知进度不伪装成零`, async ({ page, api }) => {
    await page.goto(`/#/${lane}?task_id=${running}`);
    await expect(page.locator(".lb-eval-task-title")).toContainText(running);
    if (lane !== "basic") await expect(page.locator(".lb-eval-progress__head")).toContainText("等待进度");
    await page.getByRole("button", { name: "取消任务", exact: true }).click();
    if (lane !== "basic") await page.locator(".el-message-box").getByRole("button", { name: /^(确定|确认|OK)$/ }).click();
    await expect.poll(() => api.submissions.some((item) => item.path.endsWith(`/${running}/cancel`))).toBe(true);
    await expect(page.locator(".lb-eval-detail > header")).toContainText("已中断");
  });

  test(`${title}：四种屏宽、详情与暗色主题`, async ({ page }, testInfo) => {
    await page.goto(`/#/${lane}?task_id=${completed}`);
    await expect(page.locator(".lb-eval-task-title")).toContainText(completed);
    if (lane !== "basic") await expect(page.locator("canvas").first()).toBeVisible();
    for (const width of [1440, 1024, 768, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`${lane}-${width}.png`), fullPage: width !== 375, animations: "disabled" });
      await page.getByRole("button", { name: `新建${title}`, exact: true }).click();
      const drawer = page.getByRole("dialog", { name: `新建${title}`, exact: true });
      await expect(drawer).toBeVisible();
      expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
      if (width === 1440 || width === 375) await page.screenshot({ path: testInfo.outputPath(`${lane}-config-${width}.png`), animations: "disabled" });
      await drawer.getByRole("button", { name: "返回工作台", exact: true }).click();
      await expect(drawer).toBeHidden();
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("button", { name: /^切换主题/ }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({ path: testInfo.outputPath(`${lane}-dark.png`), fullPage: true, animations: "disabled" });
  });

  test(`${title}：空态与接口失败明确区分`, async ({ page, api }) => {
    api.scenario = "empty";
    await page.goto(`/?state=empty#/${lane}`);
    const emptyTitle = lane === "basic" ? "暂无基础评测任务" : lane === "stress" ? "暂无压测任务" : "暂无能力评测任务";
    await expect(page.getByText(emptyTitle, { exact: true })).toBeVisible();
    api.scenario = "failed";
    await page.goto(`/?state=failed#/${lane}`);
    await expect(page.locator(".lb-eval-list .el-alert")).toContainText("任务列表加载失败");
    await expect(page.getByText(emptyTitle, { exact: true })).toBeHidden();
  });

  test(`${title}：后台更新不打断焦点和勾选`, async ({ page }) => {
    await page.clock.install();
    await page.goto(`/#/${lane}?task_id=${running}`);
    await expect(page.locator(".lb-eval-task-title")).toContainText(running);
    const list = page.locator(".lb-eval-list");
    await list.locator(".el-table__body-wrapper .el-checkbox").first().click();
    const search = list.getByRole("textbox");
    await search.focus();
    const refreshed = page.waitForResponse((response) => new URL(response.url()).pathname === (lane === "basic" ? `${definition.list}/${running}` : definition.list));
    await page.clock.fastForward(lane === "basic" ? 1600 : 5100);
    await refreshed;
    await expect(search).toBeFocused();
    await expect(list.locator(".el-table__body-wrapper .el-checkbox.is-checked")).toHaveCount(1);
    await expect(list.locator(".el-loading-mask")).toBeHidden();
    await expect(page.locator(".lb-eval-task-title")).toContainText(running);
  });
}

test("基础评测：指定指标保持合法 ID", async ({ page, api }) => {
  api.seedActive = false;
  await page.goto("/#/basic");
  await page.getByRole("button", { name: "新建基础评测", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新建基础评测" });
  await drawer.getByRole("combobox", { name: "指定指标" }).press("Enter");
  await page.getByRole("option", { name: "流式规范性 (stream_spec)", exact: true }).click();
  await drawer.getByRole("heading", { name: "新建基础评测" }).click();
  await drawer.getByRole("button", { name: "返回工作台", exact: true }).click();
  await page.getByRole("button", { name: "新建基础评测", exact: true }).click();
  await expect(drawer.locator(".el-tag").filter({ hasText: "stream_spec" })).toBeVisible();
  await drawer.getByRole("button", { name: "开始基础评测", exact: true }).click();
  await expect.poll(() => api.submissions.length).toBe(1);
  expect(api.submissions[0].body.metric_ids).toEqual(["stream_spec"]);
});

test("压测评测：开环参数与高级生成字段可提交", async ({ page, api }) => {
  await page.goto("/#/stress");
  await page.getByRole("button", { name: "新建压测评测", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新建压测评测" });
  await drawer.getByRole("switch", { name: "自定义压测参数" }).press("Space");
  await drawer.getByText("开环速率", { exact: true }).click();
  await drawer.getByRole("textbox", { name: "请求速率 rate", exact: true }).fill("2,5");
  await drawer.getByRole("textbox", { name: "每档请求数 number", exact: true }).fill("10,20");
  await drawer.getByRole("button", { name: "高级参数" }).click();
  await drawer.getByLabel("temperature", { exact: true }).fill("0.2");
  await drawer.getByRole("button", { name: "开始压测评测", exact: true }).click();
  await expect.poll(() => api.submissions.length).toBe(1);
  expect(api.submissions[0].body).toMatchObject({ open_loop: true, rate: [2, 5], number: [10, 20], temperature: .2 });
});

test("压测评测：归组保留失败成员、明细与产物入口", async ({ page }) => {
  await page.goto("/#/stress");
  await page.getByRole("button", { name: "查看方案 长文本 · longalpaca", exact: true }).click();
  await expect(page.locator(".lb-eval-detail > header")).toContainText("部分失败");
  await page.getByRole("button", { name: "查看组内任务", exact: true }).click();
  await expect(page.getByRole("region", { name: "组内任务", exact: true })).toContainText("stress_ui_failed");
  await page.getByRole("tab", { name: "档位明细", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "档位明细" })).toContainText("并发 5");
  await page.goto("/?individual=1#/stress?task_id=stress_ui_completed");
  await expect(page.getByRole("link", { name: "原始结果 JSON" })).toHaveAttribute("href", /raw-result$/);
  await page.getByRole("tab", { name: "任务与产物", exact: true }).click();
  await expect(page.getByRole("link", { name: /metrics.json/ })).toHaveAttribute("href", /artifacts\/results\/metrics.json$/);
});

test("能力评测：样本参数、仅本地选择与子集覆盖", async ({ page, api }) => {
  await page.goto("/#/intelligence");
  await page.getByRole("button", { name: "新建能力评测", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新建能力评测" });
  await drawer.getByRole("switch", { name: "自定义数据集" }).press("Space");
  await drawer.getByRole("textbox", { name: "样本上限 limit" }).fill("5");
  await drawer.getByRole("textbox", { name: "评测批大小" }).fill("2");
  await drawer.getByRole("button", { name: "展开 GSM8K 子集", exact: true }).click();
  const dataset = drawer.locator(".dataset-picker__row").filter({ has: page.getByText("GSM8K", { exact: true }) });
  await dataset.getByRole("switch").press("Space");
  await drawer.getByRole("button", { name: "全部数据集", exact: true }).click();
  await expect(drawer.getByText("未下载的数据集", { exact: true })).toHaveCount(0);
  await drawer.getByRole("button", { name: "开始能力评测", exact: true }).click();
  await expect.poll(() => api.submissions.length).toBe(1);
  expect(api.submissions[0]).toEqual({ path: "/api/intelligence/tasks", body: { model_id: "ui-model", datasets: ["bbh", "gsm8k"], limit: 5, eval_batch_size: 2, dataset_args: { gsm8k: { subset_list: ["main"] } } } });
});

test("压测评测：闭环档位校验与参数保持一致", async ({ page, api }) => {
  await page.goto("/#/stress");
  await page.getByRole("button", { name: "新建压测评测", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新建压测评测" });
  await drawer.getByRole("switch", { name: "自定义压测参数" }).press("Space");
  await drawer.getByRole("textbox", { name: "并发档位 parallel", exact: true }).fill("1,2");
  await drawer.getByRole("textbox", { name: "每档请求数 number", exact: true }).fill("10");
  await drawer.getByRole("button", { name: "开始压测评测", exact: true }).click();
  await expect(page.getByText("闭环模式下 parallel 与 number 必须一一对应。", { exact: true })).toBeVisible();
  expect(api.submissions).toHaveLength(0);
  await drawer.getByRole("textbox", { name: "每档请求数 number", exact: true }).fill("10,20");
  await drawer.getByRole("button", { name: "开始压测评测", exact: true }).click();
  await expect.poll(() => api.submissions.length).toBe(1);
  expect(api.submissions[0].body).toMatchObject({ open_loop: false, parallel: [1, 2], number: [10, 20] });
});

test("能力评测：缺失得分不变零，能力类别和报告可访问", async ({ page }) => {
  await page.goto("/#/intelligence?task_id=intel_ui_completed");
  await expect(page.locator(".lb-intel-results")).toContainText("82.5%");
  await expect(page.locator(".lb-intel-results")).toContainText("未取得分数");
  await expect(page.getByRole("link", { name: "打开报告", exact: true })).toHaveAttribute("href", "/api/intelligence/reports/intel_ui_completed");
  await page.getByRole("tab", { name: "能力维度", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "能力维度" })).toContainText("未取得分数");
});
