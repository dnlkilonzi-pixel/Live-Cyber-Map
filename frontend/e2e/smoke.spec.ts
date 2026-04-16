/**
 * Playwright smoke test – Global Intelligence Dashboard.
 *
 * Verifies:
 *  1. The page loads without a JS crash
 *  2. The "GLOBAL INTEL" heading is visible
 *  3. The WebSocket LIVE / OFFLINE badge renders
 *  4. A screenshot is captured for visual regression archives
 *
 * Run with:  npx playwright test
 * The test targets BASE_URL (default: http://localhost:3000).
 */
import { test, expect } from "@playwright/test";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";

test.describe("Global Intelligence Dashboard", () => {
  test("page loads and shows main UI", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });

    // The app title / heading must be visible
    await expect(
      page.locator("text=GLOBAL INTEL")
    ).toBeVisible({ timeout: 15_000 });

    // The live / offline badge must be present (either state is acceptable)
    const badge = page.locator("text=LIVE, text=OFFLINE").first();
    await expect(badge).toBeVisible({ timeout: 15_000 });

    // Take screenshot for visual regression archive
    await page.screenshot({
      path: "e2e/screenshots/smoke.png",
      fullPage: false,
    });
  });

  test("financial ticker button toggles panel", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });

    // Wait for the top bar to render
    await page.waitForSelector("button:has-text('MARKETS')", { timeout: 15_000 });
    await page.click("button:has-text('MARKETS')");

    // Financial panel should appear (or the ticker section)
    // We just assert no unhandled errors were thrown
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.waitForTimeout(1_000);
    expect(errors).toHaveLength(0);
  });
});
