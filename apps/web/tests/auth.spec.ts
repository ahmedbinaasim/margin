import { expect, test } from "@playwright/test";

test.describe("dashboard sign-in", () => {
  test("email + dev-mode code unlocks dashboard", async ({ page }) => {
    test.skip(!process.env.MARGIN_API_RUNNING, "needs api server in dev mode (Resend unset)");
    await page.goto("/app");
    await page.getByPlaceholder(/example.com/i).fill("playwright@margin.dev");
    await page.getByRole("button", { name: /send code/i }).click();
    // Dev-mode code is rendered into the hint block.
    const hint = page.getByText(/Your code:/i);
    await expect(hint).toBeVisible();
    const text = (await hint.innerText()) || "";
    const match = text.match(/(\d{6})/);
    expect(match).not.toBeNull();
    const code = match![1];
    await page.getByPlaceholder("123456").fill(code);
    await page.getByRole("button", { name: /verify/i }).click();
    await expect(page.getByRole("heading", { name: /Dashboard/i })).toBeVisible();
  });
});
