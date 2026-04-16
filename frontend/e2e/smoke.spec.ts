/**
 * Playwright smoke test – Global Intelligence Dashboard.
 *
 * Verifies:
 *  1. The page loads without a JS crash
 *  2. The "GLOBAL INTEL" heading is visible
 *  3. The WebSocket LIVE / OFFLINE badge renders
 *  4. A screenshot is captured for visual regression archives
 *  5. Injecting a WebSocket `alert` message shows the red notification badge
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
    const badge = page
      .locator("text=LIVE")
      .or(page.locator("text=OFFLINE"))
      .first();
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

  test("alert badge appears after injecting a WebSocket alert message", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });

    // Wait for the ALERTS button to be present
    await page.waitForSelector("button:has-text('ALERTS')", { timeout: 15_000 });

    // Intercept the WebSocket and inject a fake alert message after connection
    await page.evaluate(() => {
      const OriginalWS = window.WebSocket;
      // Wrap the WebSocket constructor to intercept the first connection
      (window as unknown as Record<string, unknown>)["__injectAlert"] = (ws: WebSocket) => {
        const payload = JSON.stringify({
          type: "alert",
          data: {
            rule_id: 999,
            rule_name: "E2E Test Rule",
            message: "Test alert fired",
            fired_at: Date.now() / 1000,
          },
        });
        // Dispatch the message as if it came from the server
        ws.dispatchEvent(new MessageEvent("message", { data: payload }));
      };
      // Override WebSocket to capture the instance
      class PatchedWS extends OriginalWS {
        constructor(url: string | URL, protocols?: string | string[]) {
          super(url, protocols);
          this.addEventListener("open", () => {
            (window as unknown as Record<string, unknown>)["__wsInstance"] = this;
          });
        }
      }
      window.WebSocket = PatchedWS as typeof WebSocket;
    });

    // Re-navigate so the patched WebSocket constructor is used
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForSelector("button:has-text('ALERTS')", { timeout: 15_000 });

    // Wait for WS connection, then inject the alert
    await page.waitForFunction(() => (window as unknown as Record<string, unknown>)["__wsInstance"] !== undefined, { timeout: 10_000 });
    await page.evaluate(() => {
      const ws = (window as unknown as Record<string, unknown>)["__wsInstance"] as WebSocket;
      const inject = (window as unknown as Record<string, unknown>)["__injectAlert"] as (ws: WebSocket) => void;
      inject(ws);
    });

    // The red badge (unread count) must appear on the ALERTS button
    const alertsBadge = page.locator("button:has-text('ALERTS') span.bg-red-600").first();
    await expect(alertsBadge).toBeVisible({ timeout: 5_000 });
  });
});
