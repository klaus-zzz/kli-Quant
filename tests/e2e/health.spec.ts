import { expect, test } from "@playwright/test";

// 成功路径必须经过实际开发代理和后端，不能用模拟数据代替。
test("显示开发骨架和真实健康状态", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "开发骨架" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("后端进程正常");
});

// 接口失败或返回错误结构时，页面不能声称后端正常。
for (const response of [
  { status: 503, body: { status: "error" } },
  { status: 200, body: null },
]) {
  test(`异常响应 ${response.status} 显示不可用`, async ({ page }) => {
    await page.route("**/api/health", (route) =>
      route.fulfill({ status: response.status, json: response.body }),
    );
    await page.goto("/");
    await expect(page.getByRole("status")).toHaveText(
      "后端暂不可用，请稍后刷新页面。",
    );
  });
}
