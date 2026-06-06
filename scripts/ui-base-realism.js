const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const reportDir = path.join(root, "reports", "base-realism");

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
    env: { ...process.env, AEGIS_WEB_PACE_SECONDS: process.env.AEGIS_WEB_PACE_SECONDS || "0" },
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

async function selectFirstSurgeStep(page) {
  const max = Number(await page.locator("#stepRange").getAttribute("max"));
  for (let index = 0; index <= max; index += 1) {
    await page.locator("#stepRange").evaluate((el, value) => {
      el.value = String(value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, index);
    const raw = JSON.parse(await page.locator("#rawEvent").innerText());
    if (raw.dfm && (raw.dfm.dfm_surge_triggered === true || raw.dfm.dfm_surge_triggered === "true")) {
      return { index, raw };
    }
  }
  return null;
}

(async () => {
  ensureDir(reportDir);
  const { child, baseUrl } = await startServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleMessages = [];
  page.on("console", (msg) => consoleMessages.push({ type: msg.type(), text: msg.text() }));
  page.on("pageerror", (error) => consoleMessages.push({ type: "pageerror", text: error.message }));

  const metrics = {
    status: "fail",
    base_url: `${baseUrl}/web/index.html`,
    failures: [],
    console_messages: consoleMessages,
    dfm_surge_highlight: false,
    market_stats_visible: false,
    raw_download_zip: false,
    final_day_180: false,
    selected_surge_step: null,
  };

  try {
    await page.goto(`${baseUrl}/web/index.html`);
    await page.waitForSelector("#strategyEditor");
    await page.click("#runButton");
    await page.locator("#commandStatus").filter({ hasText: /Run complete/ }).waitFor({ timeout: 120000 });
    const finalRaw = JSON.parse(await page.locator("#rawEvent").innerText());
    metrics.final_day_180 = Number(finalRaw.elapsed_simulated_days || 0) >= 179.9;
    if (!metrics.final_day_180) metrics.failures.push(`final replay did not end at day 180: ${finalRaw.elapsed_simulated_days}`);

    const surge = await selectFirstSurgeStep(page);
    if (!surge) {
      metrics.failures.push("no sampled DFM surge step found");
    } else {
      metrics.selected_surge_step = surge.raw.step;
      const feePill = await page.locator("#feePill").innerText();
      const marketState = await page.locator("#marketState").innerText();
      const dfmFee = await page.locator("#dfmFeeCell").innerText();
      const lpFee = await page.locator("#lpFeeCell").innerText();
      metrics.dfm_surge_highlight = /DFM fee surge/i.test(feePill)
        && /DFM fee surge/i.test(marketState)
        && dfmFee.includes("bps")
        && lpFee.includes("to CL")
        && /DFM lift/i.test(lpFee);
      if (!metrics.dfm_surge_highlight) metrics.failures.push(`DFM surge UI did not highlight selected surge: ${feePill} / ${marketState} / ${dfmFee} / ${lpFee}`);
      metrics.market_stats_visible = (await page.locator("#volumeCell").innerText()).includes("$")
        && /\d/.test(await page.locator("#tradesCell").innerText())
        && (await page.locator("#neutralityCell").innerText()).length > 0;
      if (!metrics.market_stats_visible) metrics.failures.push("market stats were not visible at selected surge step");
    }

    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.click("#downloadDataButton");
    const download = await downloadPromise;
    metrics.raw_download_zip = download.suggestedFilename().endsWith(".zip");
    if (!metrics.raw_download_zip) metrics.failures.push(`raw download was not a zip: ${download.suggestedFilename()}`);
    if (consoleMessages.length) metrics.failures.push("console/page errors were emitted");
    metrics.status = metrics.failures.length ? "fail" : "pass";
  } finally {
    const screenshotPath = path.join(reportDir, "ui-base-realism.png");
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
    metrics.screenshot = path.relative(root, screenshotPath);
    await browser.close();
    child.kill();
  }

  const jsonPath = path.join(reportDir, "ui-base-realism.json");
  const mdPath = path.join(reportDir, "ui-base-realism.md");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# UI Base Realism Check",
    "",
    `Status: ${metrics.status}`,
    "",
    `- Final day 180: ${metrics.final_day_180}`,
    `- DFM surge highlight: ${metrics.dfm_surge_highlight}`,
    `- Market stats visible: ${metrics.market_stats_visible}`,
    `- Raw ZIP download: ${metrics.raw_download_zip}`,
    `- Selected surge step: ${metrics.selected_surge_step}`,
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
