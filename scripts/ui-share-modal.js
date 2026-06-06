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

function rel(file) {
  return path.relative(root, file);
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
    env: { ...process.env, AEGIS_WEB_PACE_SECONDS: "0" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const baseUrl = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 80; i += 1) {
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

async function publishAttempt(page, strategyName) {
  await page.goto(`${page.baseUrl}/web/index.html`);
  await page.waitForSelector("#strategyEditor");
  await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));
  await page.selectOption("#bundleSelect", "smoke");
  await page.fill("#strategyNameInput", strategyName);
  await page.click("#runButton");
  await page.locator("#commandStatus").filter({ hasText: /Run complete/ }).waitFor({ timeout: 60000 });
  await page.click("#submitButton");
  await page.locator("#shareModal").waitFor({ state: "visible", timeout: 10000 });
}

async function cardIsNonblank(page) {
  return page.locator("#shareCardCanvas").evaluate((canvas) => {
    const ctx = canvas.getContext("2d");
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 0; i < data.length; i += 64) {
      if (data[i] || data[i + 1] || data[i + 2]) return true;
    }
    return false;
  });
}

async function noHorizontalOverflow(page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll("body *")]
      .filter((el) => {
        const box = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return style.display !== "none" && box.width > 0 && (box.left < -1 || box.right > width + 1);
      })
      .map((el) => `${el.tagName.toLowerCase()}#${el.id || ""}.${[...el.classList].join(".")}`)
      .slice(0, 10);
  });
}

(async () => {
  ensureDir(uxDir);
  const { child, baseUrl } = await startServer();
  const browser = await chromium.launch({ headless: true });
  const metrics = {
    status: "fail",
    base_url: `${baseUrl}/web/index.html`,
    modal_visible_after_publish: false,
    copy_is_clean: false,
    intent_uses_text_plus_url: false,
    card_nonblank: false,
    copy_button_works: false,
    download_button_works: false,
    dismissible: false,
    mobile_no_overflow: false,
    screenshots: [],
    failures: [],
    console_messages: [],
  };

  try {
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
    await context.grantPermissions(["clipboard-write"], { origin: baseUrl });
    const page = await context.newPage();
    page.baseUrl = baseUrl;
    page.on("console", (msg) => metrics.console_messages.push({ type: msg.type(), text: msg.text() }));
    page.on("pageerror", (error) => metrics.console_messages.push({ type: "pageerror", text: error.message }));
    await publishAttempt(page, "Share Modal Delta Try");
    metrics.modal_visible_after_publish = await page.locator("#shareModal").isVisible();
    const shareText = await page.locator("#shareCopy").inputValue();
    metrics.copy_is_clean = /Ranked #\d+ in the Aegis Vault Challenge/.test(shareText)
      && /[+-]\$[\d,]+/.test(shareText)
      && /[+-]\d+\.\d{2}% APR/.test(shareText)
      && shareText.includes("APR")
      && shareText.includes("ETH/USDC")
      && shareText.includes("Share Modal Delta Try")
      && !/\d+\.\d{4,}/.test(shareText);
    if (!metrics.copy_is_clean) metrics.failures.push("share copy was not clean, ranked, and attempt-specific");
    const intent = await page.evaluate(() => currentIntentUrl());
    const parsedIntent = new URL(intent);
    const intentText = parsedIntent.searchParams.get("text") || "";
    const intentUrl = parsedIntent.searchParams.get("url") || "";
    metrics.intent_uses_text_plus_url = parsedIntent.hostname === "twitter.com"
      && intentText.includes("Aegis Vault Challenge")
      && Boolean(intentUrl)
      && !intentText.includes(intentUrl);
    if (!metrics.intent_uses_text_plus_url) metrics.failures.push("X intent did not separate post text from URL");
    metrics.card_nonblank = await cardIsNonblank(page);
    if (!metrics.card_nonblank) metrics.failures.push("share card canvas was blank");
    await page.click("#copyShareButton");
    await page.locator("#commandStatus").filter({ hasText: /Share text copied/ }).waitFor({ timeout: 5000 });
    metrics.copy_button_works = true;
    const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
    await page.click("#downloadShareCardButton");
    const download = await downloadPromise;
    metrics.download_button_works = download.suggestedFilename().endsWith(".png");
    if (!metrics.download_button_works) metrics.failures.push("download card did not create a PNG download");
    const desktopShot = path.join(uxDir, "share-modal-desktop.png");
    await page.screenshot({ path: desktopShot, fullPage: true });
    metrics.screenshots.push(rel(desktopShot));
    await page.click("#closeShareModalButton");
    await page.locator("#shareModal").waitFor({ state: "hidden", timeout: 5000 });
    metrics.dismissible = true;
    await context.close();

    const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobile = await mobileContext.newPage();
    mobile.baseUrl = baseUrl;
    mobile.on("console", (msg) => metrics.console_messages.push({ type: msg.type(), text: msg.text() }));
    mobile.on("pageerror", (error) => metrics.console_messages.push({ type: "pageerror", text: error.message }));
    await publishAttempt(mobile, "Mobile Share Try");
    const overflow = await noHorizontalOverflow(mobile);
    metrics.mobile_no_overflow = overflow.length === 0;
    if (overflow.length) metrics.failures.push(`mobile share modal overflow: ${overflow.join(", ")}`);
    const mobileShot = path.join(uxDir, "share-modal-mobile.png");
    await mobile.screenshot({ path: mobileShot, fullPage: true });
    metrics.screenshots.push(rel(mobileShot));
    await mobileContext.close();

    if (metrics.console_messages.length) metrics.failures.push("console messages were emitted");
    metrics.status = metrics.failures.length ? "fail" : "pass";
  } finally {
    await browser.close();
    child.kill();
  }

  const jsonPath = path.join(uxDir, "share-modal-metrics.json");
  const mdPath = path.join(uxDir, "share-modal-metrics.md");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# X Share Modal Metrics",
    "",
    `Status: ${metrics.status}`,
    "",
    `- Modal visible after publish: ${metrics.modal_visible_after_publish}`,
    `- Copy is clean: ${metrics.copy_is_clean}`,
    `- Intent uses text plus URL: ${metrics.intent_uses_text_plus_url}`,
    `- Card nonblank: ${metrics.card_nonblank}`,
    `- Copy button works: ${metrics.copy_button_works}`,
    `- Download button works: ${metrics.download_button_works}`,
    `- Dismissible: ${metrics.dismissible}`,
    `- Mobile no overflow: ${metrics.mobile_no_overflow}`,
    "",
    "Screenshots:",
    "",
    ...metrics.screenshots.map((file) => `- ${file}`),
    "",
    metrics.failures.length ? "Failures:" : "Failures: none.",
    "",
    ...metrics.failures.map((failure) => `- ${failure}`),
    "",
  ].join("\n"));
  console.log(JSON.stringify({ status: metrics.status, evidence: [rel(jsonPath), rel(mdPath)], screenshots: metrics.screenshots, failures: metrics.failures }, null, 2));
  if (metrics.status !== "pass") process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
