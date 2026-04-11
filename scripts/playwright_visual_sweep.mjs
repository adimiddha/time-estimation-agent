import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium, webkit, devices } from 'playwright';

const baseUrl = process.env.SWEEP_URL || 'https://untangle.run';
const outDir = path.resolve(process.cwd(), process.env.SWEEP_OUTDIR || 'artifacts/playwright');

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function runScenario(name, browserType, contextOptions) {
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext({
    ...contextOptions,
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  await context.tracing.start({ screenshots: true, snapshots: true });

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, `${name}-01-home.png`), fullPage: true });

    const brainDump = page.locator('#brain-dump');
    if (await brainDump.count()) {
      await brainDump.fill(
        'It is 2pm. I need to finish proposal, respond to 6 emails, and prep for a 5pm call. I want to stop by 7pm.'
      );
      await page.screenshot({ path: path.join(outDir, `${name}-02-filled-brain-dump.png`), fullPage: true });

      const planBtn = page.locator('#plan-btn');
      await planBtn.waitFor({ state: 'visible', timeout: 10_000 });
      const hasReadyClass = await planBtn.evaluate((el) => el.classList.contains('plan-btn--ready'));
      if (!hasReadyClass) {
        throw new Error('Expected #plan-btn to have .plan-btn--ready after typing in brain dump');
      }
    }

    const planBtn = page.locator('#plan-btn');
    if (await planBtn.count()) {
      await planBtn.click({ timeout: 10_000 });
      // Either clarify, loading, or (rare) straight to planner
      await page.waitForSelector(
        '#followup-clarify-screen, #loading-screen, #plan-ready-screen, #draft-section',
        { timeout: 60_000 }
      );
      // If follow-up appears, skip to planning path
      const clarify = page.locator('#followup-clarify-screen');
      if (await clarify.isVisible().catch(() => false)) {
        await page.locator('#followup-skip-link').click();
      }
      // Brief "Plan ready" handoff (may flash quickly)
      const planReady = page.locator('#plan-ready-screen');
      try {
        await planReady.waitFor({ state: 'visible', timeout: 15_000 });
        await page.screenshot({ path: path.join(outDir, `${name}-03-plan-ready.png`), fullPage: true });
      } catch {
        // API may be very fast; draft might appear before screenshot
      }
      await page.locator('#draft-section').waitFor({ state: 'visible', timeout: 120_000 });
    }

    await page.screenshot({ path: path.join(outDir, `${name}-04-post-plan.png`), fullPage: true });
  } finally {
    await context.tracing.stop({ path: path.join(outDir, `${name}-trace.zip`) });
    await context.close();
    await browser.close();
  }
}

await ensureDir(outDir);

await runScenario('desktop', chromium, {
  viewport: { width: 1440, height: 1000 },
  userAgent:
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
});

await runScenario('iphone13', webkit, {
  ...devices['iPhone 13'],
});

console.log(`Visual sweep complete for ${baseUrl}`);
console.log(`Artifacts saved to: ${outDir}`);
