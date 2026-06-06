const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const uxDir = path.join(root, "reports", "ux");

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on("error", reject);
  });
}

async function startServer() {
  const port = await freePort();
  const child = spawn("python3", ["-m", "aegis_challenge.web_server", "--port", String(port)], {
    cwd: root,
    env: { ...process.env, AEGIS_WEB_PACE_SECONDS: process.env.AEGIS_WEB_PACE_SECONDS || "35" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const baseUrl = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 100; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return { child, baseUrl };
    } catch (_) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  child.kill();
  throw new Error("Aegis web server did not start");
}

async function pollJob(page, jobId, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  let current;
  do {
    current = await page.evaluate(async (id) => {
      const response = await fetch(`/api/run/progress?job_id=${encodeURIComponent(id)}`);
      return response.json();
    }, jobId);
    if (current.status !== "running") return current;
    await page.waitForTimeout(1000);
  } while (Date.now() < deadline);
  throw new Error(`job timed out: ${jobId}`);
}

(async () => {
  ensureDir(uxDir);
  const { child, baseUrl } = await startServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleMessages = [];
  page.on("console", (msg) => consoleMessages.push({ type: msg.type(), text: msg.text() }));
  page.on("pageerror", (error) => consoleMessages.push({ type: "pageerror", text: error.message }));

  const metrics = {
    status: "fail",
    base_url: `${baseUrl}/web/index.html`,
    horizon_days: null,
    step_length_seconds: null,
    run_duration_ms: null,
    progress_update_count: 0,
    publish_share_verified: false,
    share_modal_visible: false,
    share_card_nonblank: false,
    anonymous_second_run_blocked: false,
    failures: [],
    console_messages: consoleMessages,
  };

  try {
    await page.goto(`${baseUrl}/web/index.html`);
    await page.waitForSelector("#strategyEditor");
    await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));
    if ((await page.locator("#bundleSelect").inputValue()) !== "competition_6m") metrics.failures.push("default bundle is not competition_6m");
    if (!(await page.locator("#horizonMetric").innerText()).includes("180")) metrics.failures.push("horizon metric does not show 180 days");
    const firstViewportText = await page.locator("main").innerText();
    for (const text of ["100,000 USDC", "ETH/USDC", "USD profit", "ETH exposure"]) {
      if (!firstViewportText.includes(text)) metrics.failures.push(`missing money-first first viewport text: ${text}`);
    }

    await page.evaluate(() => {
      window.__progressLabels = [];
      window.__aprLabels = [];
      new MutationObserver(() => window.__progressLabels.push(document.querySelector("#progressLabel")?.textContent || ""))
        .observe(document.querySelector("#progressLabel"), { childList: true, characterData: true, subtree: true });
      new MutationObserver(() => window.__aprLabels.push(document.querySelector("#aprMetric")?.textContent || ""))
        .observe(document.querySelector("#aprMetric"), { childList: true, characterData: true, subtree: true });
    });

    const started = Date.now();
    await page.click("#runButton");
    await page.locator("#cancelButton").waitFor({ state: "visible" });
    await page.waitForFunction(() => !document.querySelector("#cancelButton").disabled);
    await page.waitForFunction(() => (document.querySelector("#progressLabel")?.textContent || "").match(/Day (?!0\\.0)/));
    await page.waitForFunction(() => new Set((window.__aprLabels || []).filter(Boolean)).size >= 2);
    metrics.apr_updates_before_completion = await page.evaluate(() => Array.from(new Set((window.__aprLabels || []).filter(Boolean))));
    if (metrics.apr_updates_before_completion.length < 2) metrics.failures.push("APR did not update before run completion");
    await page.locator("#commandStatus").filter({ hasText: /Run complete/ }).waitFor({ timeout: 130000 });
    metrics.run_duration_ms = Date.now() - started;
    metrics.progress_update_count = await page.evaluate(() => window.__progressLabels.length);
    metrics.apr_update_count = await page.evaluate(() => window.__aprLabels.length);
    if (metrics.run_duration_ms < 30000 || metrics.run_duration_ms > 120000) metrics.failures.push(`run duration outside target: ${metrics.run_duration_ms}`);
    if (metrics.progress_update_count < 5) metrics.failures.push(`too few progress updates: ${metrics.progress_update_count}`);
    if (metrics.apr_update_count < 2) metrics.failures.push(`too few APR updates: ${metrics.apr_update_count}`);
    const finalText = await page.locator("body").innerText();
    const finalProgressLabel = await page.locator("#progressLabel").innerText();
    const finalProgressWidth = await page.locator("#horizonProgress").evaluate((el) => getComputedStyle(el).width);
    metrics.final_progress_label = finalProgressLabel;
    metrics.final_progress_width = finalProgressWidth;
    if (!/day\s+18[0-9](\.0)?\s+of\s+180/i.test(finalProgressLabel)) metrics.failures.push(`final progress label not at horizon: ${finalProgressLabel}`);
    for (const text of ["17,280 steps", "Six-month ETH/USDC replay", "USD profit", "ETH exposure", "LTV"]) {
      if (!finalText.includes(text)) metrics.failures.push(`missing final long-horizon text: ${text}`);
    }
    const rawEvent = await page.locator("#rawEvent").innerText();
    for (const text of ["initial_balance_usdc", "eth_price_usdc", "net_profit_usd_after_penalties", "apr_pct", "elapsed_simulated_days", "eth_exposure_usd"]) {
      if (!rawEvent.includes(text)) metrics.failures.push(`final replay missing money field: ${text}`);
    }
    metrics.horizon_days = 180;
    metrics.step_length_seconds = 900;
    await page.click("#submitButton");
    await page.locator("#commandStatus").filter({ hasText: /Published|Leaderboard updated/ }).waitFor({ timeout: 15000 });
    await page.locator("#shareModal").waitFor({ state: "visible", timeout: 5000 });
    metrics.share_modal_visible = true;
    const shareText = await page.locator("#shareCopy").inputValue();
    const leaderboardText = await page.locator("#leaderboardRows").innerText();
    metrics.publish_share_verified = /Ranked #\d+ in the Aegis Vault Challenge/.test(shareText) && leaderboardText.includes("@anonymous") && !/\d+\.\d{4,}/.test(shareText);
    if (!metrics.publish_share_verified) metrics.failures.push("long-run publish/share/leaderboard state missing expected social details");
    metrics.share_card_nonblank = await page.locator("#shareCardCanvas").evaluate((canvas) => {
      const ctx = canvas.getContext("2d");
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 0; i < data.length; i += 64) {
        if (data[i] || data[i + 1] || data[i + 2]) return true;
      }
      return false;
    });
    if (!metrics.share_card_nonblank) metrics.failures.push("share card canvas was blank");

    await page.click("#closeShareModalButton");
    await page.locator("#shareModal").waitFor({ state: "hidden", timeout: 5000 });
    await page.click("#runButton");
    await page.locator("#commandStatus").filter({ hasText: /Sign in with X to try again/ }).waitFor({ timeout: 15000 });
    metrics.anonymous_second_run_blocked = true;
    if (await page.locator("#submitButton").isDisabled()) metrics.failures.push("anonymous login wall did not preserve publishing latest run");
    if (consoleMessages.length) metrics.failures.push("console messages were emitted");

    metrics.status = metrics.failures.length ? "fail" : "pass";
  } finally {
    const screenshotPath = path.join(uxDir, "progressive-final.png");
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
    metrics.screenshot = path.relative(root, screenshotPath);
    await browser.close();
    child.kill();
  }

  const jsonPath = path.join(uxDir, "progressive-metrics.json");
  const mdPath = path.join(uxDir, "progressive-metrics.md");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# Progressive Six-Month Metrics",
    "",
    `Status: ${metrics.status}`,
    "",
    `- Horizon days: ${metrics.horizon_days}`,
    `- Step length seconds: ${metrics.step_length_seconds}`,
    `- Run duration ms: ${metrics.run_duration_ms}`,
    `- Progress updates: ${metrics.progress_update_count}`,
    `- APR updates: ${metrics.apr_update_count}`,
    `- APR values before completion: ${(metrics.apr_updates_before_completion || []).join(", ")}`,
    `- Publish/share verified: ${metrics.publish_share_verified}`,
    `- Share modal visible: ${metrics.share_modal_visible}`,
    `- Share card nonblank: ${metrics.share_card_nonblank}`,
    `- Anonymous second run blocked: ${metrics.anonymous_second_run_blocked}`,
    `- Screenshot: ${metrics.screenshot}`,
    "",
    metrics.failures.length ? "Failures:" : "Failures: none.",
    "",
    ...metrics.failures.map((failure) => `- ${failure}`),
    "",
  ].join("\n"));
  console.log(JSON.stringify({ status: metrics.status, evidence: [path.relative(root, jsonPath), path.relative(root, mdPath)], failures: metrics.failures }, null, 2));
  if (metrics.status !== "pass") process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
