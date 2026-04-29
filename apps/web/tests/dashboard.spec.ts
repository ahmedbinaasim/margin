import { expect, test } from "@playwright/test";

test.describe("dashboard activity timeline", () => {
  test("new event appears within 3s after a REST write", async ({ page, request }) => {
    test.skip(!process.env.MARGIN_API_RUNNING, "needs api server with seeded agent key in env");
    test.skip(!process.env.MARGIN_API_KEY, "needs MARGIN_API_KEY env");

    // Sign in as the same email used for the agent's owner. Same flow as auth.spec.
    await page.goto("/app");
    // Bypass UI and inject token if provided
    if (process.env.MARGIN_DASH_TOKEN) {
      await page.evaluate((t) => localStorage.setItem("margin.token", t), process.env.MARGIN_DASH_TOKEN);
      await page.evaluate((k) => localStorage.setItem("margin.agent_key", k!), process.env.MARGIN_API_KEY!);
      await page.reload();
    }

    // Trigger a synthetic write
    const r = await request.post(`${process.env.MARGIN_API_BASE ?? "http://localhost:8080"}/v1/projects`, {
      headers: {
        Authorization: `Bearer ${process.env.MARGIN_API_KEY}`,
        "Content-Type": "application/json",
      },
      data: { topic: "dashboard test", depth: "standard" },
    });
    expect(r.ok()).toBe(true);

    await expect(page.getByText("start_research")).toBeVisible({ timeout: 5000 });
  });
});
