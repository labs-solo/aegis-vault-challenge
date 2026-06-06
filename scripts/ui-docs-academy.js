const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const reportDir = path.join(root, "reports", "docs-academy");
let baseUrl;

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
    stdio: ["ignore", "pipe", "pipe"],
  });
  baseUrl = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 80; i += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return child;
    } catch (_) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  child.kill();
  throw new Error("Aegis web server did not start");
}

async function noOverflow(page, name) {
  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const visible = (el) => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    return [...document.querySelectorAll("body *")]
      .filter(visible)
      .filter((el) => {
        const box = el.getBoundingClientRect();
        return box.left < -1 || box.right > width + 1;
      })
      .slice(0, 12)
      .map((el) => `${el.tagName.toLowerCase()}#${el.id || ""}.${[...el.classList].join(".")}`);
  });
  if (overflow.length) throw new Error(`${name}: horizontal overflow ${overflow.join(", ")}`);
}

async function checkLinks(page) {
  const failures = await page.evaluate(async () => {
    const broken = [];
    for (const link of document.querySelectorAll("a[href]")) {
      const href = link.getAttribute("href");
      if (href.startsWith("#")) {
        if (!document.querySelector(href)) broken.push(`missing hash ${href}`);
        continue;
      }
      const target = new URL(href, location.href);
      const hash = target.hash;
      target.hash = "";
      const response = await fetch(target.href);
      if (!response.ok) {
        broken.push(`${href}: ${response.status}`);
        continue;
      }
      if (hash) {
        const markup = await response.text();
        if (!markup.includes(`id="${hash.slice(1)}"`)) broken.push(`missing hash ${href}`);
      }
    }
    return broken;
  });
  if (failures.length) throw new Error(`broken docs links: ${failures.join(", ")}`);
}

async function accessibilitySmoke(page, name) {
  const failures = await page.evaluate(() => {
    const visible = (el) => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    const accessibleName = (el) => {
      const labelledBy = el.getAttribute("aria-labelledby");
      if (labelledBy) {
        return labelledBy
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent || "")
          .join(" ")
          .trim();
      }
      return (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "").trim();
    };
    const issues = [];
    if (document.documentElement.lang !== "en") issues.push("html lang must be en");
    if (document.querySelectorAll("h1").length !== 1) issues.push("exactly one h1 required");
    for (const selector of ["aside[aria-label='Academy navigation']", "nav[aria-label='Docs sections']", "main"]) {
      if (!document.querySelector(selector)) issues.push(`missing landmark ${selector}`);
    }
    for (const el of [...document.querySelectorAll("a, button, input")].filter(visible)) {
      if (!accessibleName(el)) issues.push(`visible control missing accessible name: ${el.tagName.toLowerCase()}#${el.id || ""}`);
    }
    return issues;
  });
  if (failures.length) throw new Error(`${name}: accessibility smoke failures ${failures.join("; ")}`);

  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return { ok: false, selector: "none", outline: "none" };
    const style = getComputedStyle(active);
    return {
      ok: style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) >= 2,
      selector: `${active.tagName.toLowerCase()}#${active.id || ""}`,
      outline: `${style.outlineWidth} ${style.outlineStyle} ${style.outlineColor}`,
    };
  });
  if (!focus.ok) throw new Error(`${name}: keyboard focus indicator missing on ${focus.selector}`);
}

async function checkDocsViewport(browser, name, viewport) {
  const page = await browser.newPage({ viewport });
  const consoleMessages = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleMessages.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on("pageerror", (error) => consoleMessages.push(`pageerror: ${error.message}`));

  await page.goto(`${baseUrl}/web/docs.html`);
  await page.waitForSelector("text=AEGIS Strategy Academy");
  const required = [
    "text=Win in USD without making an ETH direction bet.",
    "text=What can my strategy do?",
    "text=BorrowL(amount_l)",
    "text=RepayL(amount_l",
    "text=SwapExactIn(token_in",
    "text=MintRange(lower_tick",
    "text=PlaceLimitOrder(side",
    "text=Public state guide",
    "text=No hidden fair price",
    "text=Scoring and robustness",
    "text=Strategy recipes",
    "text=DFM surge harvester",
  ];
  for (const selector of required) {
    if (!(await page.locator(selector).count())) throw new Error(`${name}: missing ${selector}`);
  }

  await page.fill("#docSearch", "DetachPosition");
  await page.waitForFunction(() => document.querySelectorAll("[data-action]:not([hidden])").length === 1);
  await page.fill("#docSearch", "");
  await page.waitForFunction(() => document.querySelectorAll("[data-action]:not([hidden])").length === 12);
  await page.locator("[data-copy]").first().click();
  await page.locator("[data-copy]").first().filter({ hasText: "Copied" }).waitFor({ timeout: 5000 });
  await checkLinks(page);
  await accessibilitySmoke(page, name);
  await noOverflow(page, name);

  const answerEvidence = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      objective: text.includes("100,000 USDC") && text.includes("ETH/USDC") && text.includes("USD profit"),
      actions: text.includes("BorrowL") && text.includes("MintRange") && text.includes("PlaceLimitOrder"),
      improvement: text.includes("Strategy recipes") && text.includes("Robustness-first ranked strategy"),
      hiddenInfo: text.includes("No hidden fair price") && text.includes("future flow"),
    };
  });
  if (Object.values(answerEvidence).some((ok) => !ok)) {
    throw new Error(`${name}: first-time clarity evidence missing ${JSON.stringify(answerEvidence)}`);
  }

  if (consoleMessages.length) throw new Error(`${name}: console errors ${consoleMessages.join("; ")}`);
  const screenshot = path.join(reportDir, `docs-${name}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  await page.close();
  return { name, viewport, screenshot: rel(screenshot), answerEvidence };
}

async function checkMainEntry(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`${baseUrl}/web/index.html`);
  await page.locator('a[aria-label="Strategy Academy"]').click();
  await page.waitForURL(/\/web\/docs\.html$/);
  await page.locator("text=AEGIS Strategy Academy").waitFor({ timeout: 5000 });
  await page.close();
}

(async () => {
  ensureDir(reportDir);
  const browser = await chromium.launch({ headless: true });
  const server = await startServer();
  let checks;
  try {
    await checkMainEntry(browser);
    checks = [
      await checkDocsViewport(browser, "desktop", { width: 1440, height: 1000 }),
      await checkDocsViewport(browser, "mobile", { width: 390, height: 844 }),
    ];
  } finally {
    await browser.close();
    server.kill();
  }

  const jsonPath = path.join(reportDir, "docs-academy-ui.json");
  const mdPath = path.join(reportDir, "docs-academy-ui.md");
  const report = {
    status: "pass",
    checks,
    gates: {
      main_app_entry: "pass",
      desktop_docs_render: "pass",
      mobile_docs_render: "pass",
      action_search_filter: "pass",
      copyable_snippets: "pass",
      accessibility_smoke: "pass",
      link_health: "pass",
      horizontal_overflow: "pass",
      first_time_clarity_evidence: "pass",
    },
  };
  fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# Docs Academy UI Evidence",
    "",
    "Status: pass.",
    "",
    "Checked:",
    "",
    "- Main app Academy link opens the in-app docs page.",
    "- Desktop and mobile docs render.",
    "- Action search filters to one result and resets to all 12 actions.",
    "- Copy buttons provide feedback.",
    "- Internal links and hashes resolve.",
    "- No horizontal overflow at 1440x1000 or 390x844.",
    "- First-time clarity evidence covers objective, strategy actions, improvement path, and hidden-info rules.",
    "",
    "Screenshots:",
    "",
    ...checks.map((check) => `- ${check.screenshot}`),
    "",
  ].join("\n"));
  console.log(JSON.stringify({ status: "pass", report: rel(jsonPath), screenshots: checks.map((check) => check.screenshot) }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
