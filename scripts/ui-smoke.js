const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
let url;
const screenshotDir = path.join(root, "reports", "screenshots");
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
    stdio: ["ignore", "pipe", "pipe"],
  });
  url = `http://127.0.0.1:${port}/web/index.html`;
  for (let i = 0; i < 80; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/health`);
      if (response.ok) return child;
    } catch (_) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  child.kill();
  throw new Error("Aegis web server did not start");
}

async function checkViewport(browser, name, viewport) {
  const page = await browser.newPage({ viewport });
  await page.goto(url);
  await page.waitForSelector("#replayChart polyline.chart-line");

  const required = [
    "text=Aegis Vault Challenge",
    "text=100,000 USDC",
    "text=ETH/USDC",
    "text=USD profit",
    "text=ETH exposure",
    "text=Why participate?",
    "text=Strategy Lab",
    "text=Six-month ETH/USDC replay: USD edge without ETH exposure",
    "text=Risk Panel",
    "text=Score Waterfall",
    "text=Leaderboard",
    "text=Run 6-month ETH/USDC simulation",
    "text=Cancel run",
    "text=Publish latest try",
    "text=Sign in with X",
    "text=Saved Tries",
    "#strategyEditor",
    "#stepRange",
    "#leaderboardRows tr",
  ];
  for (const selector of required) {
    const count = await page.locator(selector).count();
    if (!count) throw new Error(`${name}: missing selector ${selector}`);
  }

  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll("body *")]
      .filter((el) => {
        const box = el.getBoundingClientRect();
        return box.width > 0 && (box.left < -1 || box.right > width + 1);
      })
      .slice(0, 10)
      .map((el) => `${el.tagName.toLowerCase()}#${el.id || ""}.${[...el.classList].join(".")}`);
  });
  if (overflow.length) throw new Error(`${name}: horizontal overflow ${overflow.join(", ")}`);

  const imagePath = path.join(screenshotDir, `${name}.png`);
  await page.screenshot({ path: imagePath, fullPage: true });
  await page.close();
  return imagePath;
}

async function checkControls(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleMessages = [];
  page.on("console", (msg) => consoleMessages.push(`${msg.type()}: ${msg.text()}`));
  page.on("pageerror", (error) => consoleMessages.push(`pageerror: ${error.message}`));

  await page.goto(url);
  await page.waitForSelector("#strategyEditor");
  await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));

  const brokenTargets = await page.evaluate(async () => {
    const failures = [];
    for (const link of document.querySelectorAll("a[href]")) {
      const href = link.getAttribute("href");
      if (href.startsWith("#")) {
        if (!document.querySelector(href)) failures.push(`missing hash target ${href}`);
      } else {
        const response = await fetch(new URL(href, location.href).href);
        if (!response.ok) failures.push(`broken link ${href}: ${response.status}`);
      }
    }
    return failures;
  });
  if (brokenTargets.length) throw new Error(`control links failed: ${brokenTargets.join(", ")}`);

  for (const href of ["#engine", "#positions", "#leaderboard", "#audits", "#legal", "#workspace"]) {
    await page.click(`nav a[href="${href}"]`);
    await page.waitForFunction((hash) => location.hash === hash, href);
  }

  await page.selectOption("#bundleSelect", "public_train");
  if ((await page.locator("#bundleSelect").inputValue()) !== "public_train") throw new Error("scenario bundle select did not change");
  await page.selectOption("#bundleSelect", "competition_6m");
  await page.selectOption("#seedSelect", "2");
  if ((await page.locator("#seedSelect").inputValue()) !== "2") throw new Error("seed select did not change");
  await page.selectOption("#seedSelect", "1");

  await page.fill("#strategyEditor", "changed");
  await page.click("#resetButton");
  await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));
  await page.fill("#strategyEditor", "changed again");
  await page.click("#starterButton");
  await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));

  await page.click("#leaderboardButton");
  await page.locator("#commandStatus").filter({ hasText: /Leaderboard refreshed/ }).waitFor({ timeout: 5000 });

  for (const tab of ["risk", "fees", "score"]) {
    await page.click(`.tab[data-tab="${tab}"]`);
    const selected = await page.locator(`.tab[data-tab="${tab}"]`).getAttribute("aria-selected");
    if (selected !== "true") throw new Error(`tab did not select: ${tab}`);
  }

  await page.locator("#stepRange").fill("2");
  await page.locator("#stepBox").filter({ hasText: /day 90\.0/ }).waitFor({ timeout: 5000 });

  if (consoleMessages.length) throw new Error(`console messages after control pass: ${consoleMessages.join("; ")}`);
  await page.close();
}

(async () => {
  ensureDir(screenshotDir);
  ensureDir(uxDir);
  const browser = await chromium.launch({ headless: true });
  const server = await startServer();
  const screenshots = [];
  try {
    screenshots.push(await checkViewport(browser, "desktop-console", { width: 1440, height: 1000 }));
    screenshots.push(await checkViewport(browser, "laptop-console", { width: 1280, height: 800 }));
    screenshots.push(await checkViewport(browser, "tablet-console", { width: 768, height: 1024 }));
    screenshots.push(await checkViewport(browser, "mobile-console", { width: 390, height: 844 }));
    await checkControls(browser);
  } finally {
    await browser.close();
    server.kill();
  }

  const report = [
    "# Playwright UI Smoke Evidence",
    "",
    "Status: smoke pass.",
    "",
    "Checked:",
    "",
    "- Desktop, laptop, tablet, and mobile console render.",
    "- Strategy lab, USDC/ETH long-horizon replay chart, risk panel, USD score waterfall, leaderboard, and real run/publish/cancel controls exist.",
    "- Replay chart draws SVG polylines.",
    "- Navigation, docs link, selects, reset/starter/refresh buttons, score tabs, and replay scrubber respond.",
    "- No horizontal overflow was detected in checked viewports.",
    "- Screenshots were generated.",
    "",
    "Screenshots:",
    "",
    ...screenshots.map((file) => `- ${path.relative(root, file)}`),
    "",
    "Not a substitute for representative participant-trial evidence.",
    "",
  ].join("\n");
  fs.writeFileSync(path.join(uxDir, "playwright-smoke.md"), report);
  console.log(JSON.stringify({ status: "pass", screenshots: screenshots.map((file) => path.relative(root, file)) }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
