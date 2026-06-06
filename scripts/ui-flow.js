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

async function waitStatus(page, pattern, timeout = 60000) {
  await page.locator("#commandStatus").filter({ hasText: pattern }).waitFor({ timeout });
}

async function runAndWait(page, pattern = /Run complete/, timeout = 60000) {
  const started = Date.now();
  await page.click("#runButton");
  await waitStatus(page, pattern, timeout);
  return Date.now() - started;
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
    happy_path_actions_after_load: 0,
    first_run_ms: null,
    login_required_preserved_strategy: false,
    anonymous_blocked: false,
    mock_login_visible: false,
    cooldown_visible: false,
    useful_actions_enabled_during_cooldown: 0,
    publish_ms: null,
    share_intent_present: false,
    share_modal_visible: false,
    share_card_nonblank: false,
    share_intent_url_clean: false,
    leaderboard_identity_present: false,
    normal_path_cli_commands: 0,
    normal_path_file_pickers: 0,
    normal_path_manual_artifact_loads: 0,
    failures: [],
    console_messages: consoleMessages,
  };

  try {
    await page.goto(`${baseUrl}/web/index.html`);
    await page.waitForSelector("#strategyEditor");
    await page.waitForFunction(() => document.querySelector("#strategyEditor")?.value.includes("Starter strategy"));

    const firstViewportText = await page.locator("body").innerText();
    for (const text of ["Aegis Vault Challenge", "100,000 USDC", "ETH/USDC", "USD profit", "ETH exposure", "Sign in with X", "Saved Tries"]) {
      if (!firstViewportText.includes(text)) metrics.failures.push(`missing first viewport text: ${text}`);
    }
    if ((await page.locator("#bundleSelect").inputValue()) !== "competition_6m") {
      metrics.failures.push("default bundle is not competition_6m");
    }
    await page.selectOption("#bundleSelect", "smoke");
    metrics.normal_path_file_pickers = await page.locator('input[type="file"]').count();
    await page.fill("#strategyNameInput", "Starter Delta Try");

    metrics.first_run_ms = await runAndWait(page);
    metrics.happy_path_actions_after_load += 1;
    if (metrics.first_run_ms > 60000) metrics.failures.push(`first run exceeded 60s: ${metrics.first_run_ms}`);
    if (!(await page.locator("#attemptRows").innerText()).includes("Starter Delta Try")) {
      metrics.failures.push("first run did not auto-save named attempt");
    }
    const preservedStrategy = `${await page.locator("#strategyEditor").inputValue()}\n# participant edit survives login wall\n`;
    await page.fill("#strategyEditor", preservedStrategy);
    await page.click("#runButton");
    await waitStatus(page, /Sign in with X to try again/);
    metrics.happy_path_actions_after_load += 1;
    metrics.anonymous_blocked = true;
    metrics.login_required_preserved_strategy = (await page.locator("#strategyEditor").inputValue()) === preservedStrategy;
    if (!metrics.login_required_preserved_strategy) metrics.failures.push("login wall did not preserve strategy text");
    if (await page.locator("#submitButton").isDisabled()) metrics.failures.push("login wall disabled publishing latest successful attempt");

    await page.click("#loginButton");
    await page.locator("#authName").filter({ hasText: /@aegis_builder/ }).waitFor({ timeout: 5000 });
    metrics.happy_path_actions_after_load += 1;
    metrics.mock_login_visible = true;
    if (!(await page.locator("#attemptRows").innerText()).includes("@aegis_builder")) {
      metrics.failures.push("anonymous attempt did not migrate to signed-in X identity");
    }

    await page.fill("#strategyNameInput", "Signed In Delta Try");
    metrics.second_run_ms = await runAndWait(page);
    metrics.happy_path_actions_after_load += 1;
    await page.locator("#cooldownPanel").filter({ hasText: /Next simulation/i }).waitFor({ timeout: 15000 });
    metrics.cooldown_visible = await page.locator("#cooldownPanel").isVisible();
    if (!metrics.cooldown_visible) metrics.failures.push("cooldown panel was not visible after authenticated retry");
    const enabledDuringCooldown = await page.evaluate(() => {
      const ids = ["starterButton", "leaderboardButton", "resetButton", "submitButton", "loginButton", "logoutButton"];
      return ids.filter((id) => {
        const el = document.getElementById(id);
        return el && !el.hidden && !el.disabled;
      }).length;
    });
    metrics.useful_actions_enabled_during_cooldown = enabledDuringCooldown;
    if (enabledDuringCooldown < 3) metrics.failures.push(`too few useful actions enabled during cooldown: ${enabledDuringCooldown}`);

    const publishStarted = Date.now();
    await page.click("#submitButton");
    await waitStatus(page, /Published|Leaderboard updated/, 15000);
    metrics.publish_ms = Date.now() - publishStarted;
    metrics.happy_path_actions_after_load += 1;
    if (metrics.publish_ms > 15000) metrics.failures.push(`publish exceeded 15s: ${metrics.publish_ms}`);
    await page.locator("#shareModal").waitFor({ state: "visible", timeout: 5000 });
    metrics.share_modal_visible = true;
    const leaderboardText = await page.locator("#leaderboardRows").innerText();
    metrics.leaderboard_identity_present = leaderboardText.includes("@aegis_builder") && leaderboardText.includes("Signed In Delta Try");
    if (!metrics.leaderboard_identity_present) metrics.failures.push("leaderboard row did not show X handle and strategy name");
    const shareText = await page.locator("#shareCopy").inputValue();
    metrics.share_intent_present = /Ranked #\d+ in the Aegis Vault Challenge/.test(shareText) && shareText.includes("Signed In Delta Try") && !/\d+\.\d{4,}/.test(shareText);
    if (!metrics.share_intent_present) metrics.failures.push("share text missing competition, rank, or strategy name");
    const shareIntent = await page.evaluate(() => currentIntentUrl());
    const shareIntentUrl = new URL(shareIntent);
    metrics.share_intent_url_clean = Boolean(
      shareIntentUrl.hostname === "twitter.com"
        && shareIntentUrl.searchParams.get("text").includes("Aegis Vault Challenge")
        && shareIntentUrl.searchParams.get("url")
    );
    if (!metrics.share_intent_url_clean) metrics.failures.push("X intent URL did not use clean text plus separate URL");
    metrics.share_card_nonblank = await page.locator("#shareCardCanvas").evaluate((canvas) => {
      const ctx = canvas.getContext("2d");
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 0; i < data.length; i += 64) {
        if (data[i] || data[i + 1] || data[i + 2]) return true;
      }
      return false;
    });
    if (!metrics.share_card_nonblank) metrics.failures.push("share card canvas was blank");

    const postPublish = await page.evaluate(async () => {
      const auth = await fetch("/api/auth/status").then((r) => r.json());
      const attempts = await fetch("/api/attempts").then((r) => r.json());
      const leaderboard = await fetch("/api/leaderboard").then((r) => r.json());
      return { auth, attempts, leaderboard };
    });
    metrics.api_snapshot = {
      authenticated: postPublish.auth.auth.authenticated,
      attempts: postPublish.attempts.attempts.length,
      leaderboard: postPublish.leaderboard.leaderboard.length,
      block_reason: postPublish.auth.auth.block_reason,
    };
    if (!postPublish.auth.auth.authenticated) metrics.failures.push("auth/status did not report authenticated user");
    if (!postPublish.attempts.attempts.length) metrics.failures.push("attempts API returned no saved attempts");
    if (!postPublish.leaderboard.leaderboard.length) metrics.failures.push("leaderboard API returned no published row");

    if (metrics.happy_path_actions_after_load > 6) metrics.failures.push("happy path exceeded 6 actions");
    if (metrics.normal_path_file_pickers !== 0) metrics.failures.push("normal path exposes file pickers");
    if (consoleMessages.length) metrics.failures.push("console errors/messages were emitted");
    metrics.status = metrics.failures.length ? "fail" : "pass";
  } finally {
    const screenshotPath = path.join(uxDir, "flow-final.png");
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
    metrics.screenshot = rel(screenshotPath);
    await browser.close();
    child.kill();
  }

  const jsonPath = path.join(uxDir, "flow-metrics.json");
  const mdPath = path.join(uxDir, "flow-metrics.md");
  fs.writeFileSync(jsonPath, JSON.stringify(metrics, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# Website Flow Metrics",
    "",
    `Status: ${metrics.status}`,
    "",
    `- Happy-path actions after load: ${metrics.happy_path_actions_after_load}`,
    `- First run ms: ${metrics.first_run_ms}`,
    `- Anonymous blocked: ${metrics.anonymous_blocked}`,
    `- Login wall preserved strategy: ${metrics.login_required_preserved_strategy}`,
    `- Mock X login visible: ${metrics.mock_login_visible}`,
    `- Cooldown visible: ${metrics.cooldown_visible}`,
    `- Useful actions enabled during cooldown: ${metrics.useful_actions_enabled_during_cooldown}`,
    `- Publish ms: ${metrics.publish_ms}`,
    `- Share modal visible: ${metrics.share_modal_visible}`,
    `- Share card nonblank: ${metrics.share_card_nonblank}`,
    `- Share intent URL clean: ${metrics.share_intent_url_clean}`,
    `- Leaderboard identity present: ${metrics.leaderboard_identity_present}`,
    `- Share intent present: ${metrics.share_intent_present}`,
    `- CLI commands on normal path: ${metrics.normal_path_cli_commands}`,
    `- File pickers on normal path: ${metrics.normal_path_file_pickers}`,
    `- Manual artifact loads on normal path: ${metrics.normal_path_manual_artifact_loads}`,
    `- Screenshot: ${metrics.screenshot}`,
    "",
    metrics.failures.length ? "Failures:" : "Failures: none.",
    "",
    ...metrics.failures.map((failure) => `- ${failure}`),
    "",
  ].join("\n"));
  console.log(JSON.stringify({ status: metrics.status, evidence: [rel(jsonPath), rel(mdPath)], failures: metrics.failures }, null, 2));
  if (metrics.status !== "pass") process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
