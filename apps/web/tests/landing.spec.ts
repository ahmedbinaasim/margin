import { expect, test } from "@playwright/test";

test("landing page renders the hero and primitives table", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Margin");
  await expect(page.getByText("the eight primitives", { exact: false })).toBeVisible();
  // The connector URL code block is present
  const code = page.getByTestId("code-block").first();
  await expect(code).toContainText("api.margin.dev/mcp/");
});

test("copy-to-clipboard button toggles label", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  const copyBtn = page.getByRole("button", { name: /copy/i }).first();
  await copyBtn.click();
  await expect(copyBtn).toContainText(/copied/i);
});
