const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const reportDir = path.join(root, "reports", "market-engine-v2-ui");

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
    env: {
      ...process.env,
      AEGIS_WEB_PACE_SECONDS: "0",
      AEGIS_RANKED_PATH_COUNT: "20",
      AEGIS_RANKED_BUNDLE: "smoke",
    },
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

(async () => {
  ensureDir(reportDir);
  const { child, baseUrl } = await startServer();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const consoleMessages = [];
  page.on("console", (msg) => consoleMessages.push({ type: msg.type(), text: msg.text() }));
  page.on("pageerror", (error) => consoleMessages.push({ type: "pageerror", text: error.message }));
  const metrics = {
    status: "fail",
    base_url: `${baseUrl}/web/index.html`,
    failures: [],
    random_path_changed_seed: false,
    market_path_visible: false,
    raw_export_download: false,
    ranked_robustness_visible: false,
    hidden_seed_not_visible: false,
    mobile_no_horizontal_overflow: false,
    console_messages: consoleMessages,
  };
  try {
    await page.goto(`${baseUrl}/web/index.html`);
    await page.waitForSelector("#strategyEditor");
    const beforeSeed = await page.locator("#seedSelect").inputValue();
    await page.click("#randomPathButton");
    await page.waitForFunction((seed) => document.querySelector("#seedSelect").value !== seed, beforeSeed);
    metrics.random_path_changed_seed = true;
    const pathPill = await page.locator("#pathPill").innerText();
    if (!/random public path/i.test(pathPill)) metrics.failures.push(`random path pill did not update: ${pathPill}`);

    await page.selectOption("#bundleSelect", "smoke");
    await page.selectOption("#seedSelect", "1");
    await page.click("#runButton");
    await page.locator("#commandStatus").filter({ hasText: /Run complete/ }).waitFor({ timeout: 60000 });
    const raw = JSON.parse(await page.locator("#rawEvent").innerText());
    metrics.market_path_visible = Boolean(raw.market_path && raw.market_path.trade_intensity && raw.market_path.stochastic_volatility);
    if (!metrics.market_path_visible) metrics.failures.push("raw public replay lacks market_path intensity/volatility stats");
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.click("#downloadDataButton");
    const download = await downloadPromise;
    metrics.raw_export_download = download.suggestedFilename().endsWith(".zip");
    if (!metrics.raw_export_download) metrics.failures.push(`raw export download was not a zip: ${download.suggestedFilename()}`);

    await page.click("#submitButton");
    await page.locator("#rankPathCountCell").filter({ hasText: /20 hidden paths/ }).waitFor({ timeout: 90000 });
    metrics.ranked_robustness_visible = /20 hidden paths/.test(await page.locator("#rankPathCountCell").innerText())
      && /\$|-\+?/.test(await page.locator("#rankMedianCell").innerText());
    if (!metrics.ranked_robustness_visible) metrics.failures.push("ranked robustness panel did not show hidden-path aggregate metrics");

    const bodyText = await page.locator("body").innerText();
    metrics.hidden_seed_not_visible = !/hidden_seeds|"seed":\s*2\d{9}/i.test(bodyText);
    if (!metrics.hidden_seed_not_visible) metrics.failures.push("UI exposed hidden seed details");
    await page.click("#closeShareModalBottomButton").catch(() => {});
    await page.setViewportSize({ width: 390, height: 844 });
    metrics.mobile_no_horizontal_overflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2);
    if (!metrics.mobile_no_horizontal_overflow) metrics.failures.push("mobile layout has horizontal overflow");
    if (consoleMessages.length) metrics.failures.push("console/page errors were emitted");
    metrics.status = metrics.failures.length ? "fail" : "pass";
  } finally {
    const screenshotPath = path.join(reportDir, "market-engine-v2-ui.png");
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
    metrics.screenshot = path.relative(root, screenshotPath);
    await browser.close();
    child.kill();
  }
  const jsonPath = path.join(reportDir, "market-engine-v2-ui.json");
  const mdPath = path.join(reportDir, "market-engine-v2-ui.md");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# Market Engine V2 UI Check",
    "",
    `Status: ${metrics.status}`,
    "",
    `- Random path changed seed: ${metrics.random_path_changed_seed}`,
    `- Market path visible: ${metrics.market_path_visible}`,
    `- Raw export download: ${metrics.raw_export_download}`,
    `- Ranked robustness visible: ${metrics.ranked_robustness_visible}`,
    `- Hidden seed not visible: ${metrics.hidden_seed_not_visible}`,
    `- Mobile no horizontal overflow: ${metrics.mobile_no_horizontal_overflow}`,
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
