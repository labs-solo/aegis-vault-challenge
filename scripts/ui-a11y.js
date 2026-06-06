const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
let url;
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

async function auditViewport(browser, name, viewport) {
  const page = await browser.newPage({ viewport });
  await page.goto(url);
  await page.waitForSelector("#replayChart polyline.chart-line");

  const result = await page.evaluate(() => {
    const failures = [];
    const notes = [];
    const selectorName = (el) => `${el.tagName.toLowerCase()}#${el.id || ""}.${[...el.classList].join(".")}`;
    const visible = (el) => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0;
    };
    const accessibleName = (el) => {
      const labelledBy = el.getAttribute("aria-labelledby");
      if (labelledBy) {
        return labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ").trim();
      }
      return (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || "").trim();
    };
    const rgba = (color) => {
      const match = color.match(/rgba?\(([^)]+)\)/);
      if (!match) return null;
      const parts = match[1].split(",").map((p) => Number(p.trim()));
      return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
    };
    const srgb = (value) => {
      const channel = value / 255;
      return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    };
    const luminance = ([r, g, b]) => 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b);
    const contrast = (fg, bg) => {
      const fgLum = luminance(fg);
      const bgLum = luminance(bg);
      const lighter = Math.max(fgLum, bgLum);
      const darker = Math.min(fgLum, bgLum);
      return (lighter + 0.05) / (darker + 0.05);
    };

    if (document.documentElement.lang !== "en") failures.push("html language must be en");
    if (document.querySelectorAll("h1").length !== 1) failures.push("page must have exactly one h1");
    for (const selector of ["nav[aria-label]", "main", "aside[aria-label]"]) {
      if (!document.querySelector(selector)) failures.push(`missing landmark ${selector}`);
    }
    for (const selector of ["svg[role='img'][aria-label]", "[role='tablist'][aria-label]", "input[type='range'][aria-label]"]) {
      if (!document.querySelector(selector)) failures.push(`missing labelled widget ${selector}`);
    }

    const controls = [...document.querySelectorAll("a, button, input, select, textarea, label.file-label")].filter(visible);
    for (const el of controls) {
      if (!accessibleName(el)) failures.push(`interactive control has no accessible name: ${selectorName(el)}`);
    }

    const tabs = [...document.querySelectorAll("[role='tab']")];
    if (!tabs.length) failures.push("score view tabs must use role=tab");
    if (tabs.filter((tab) => tab.getAttribute("aria-selected") === "true").length !== 1) {
      failures.push("exactly one tab must be aria-selected=true");
    }

    const backgroundFor = (el) => {
      let node = el;
      while (node && node.nodeType === Node.ELEMENT_NODE) {
        const style = getComputedStyle(node);
        if (style.backgroundImage && style.backgroundImage !== "none") {
          if (style.backgroundImage.includes("255, 135, 40") || style.backgroundImage.includes("#ff8728")) {
            return [255, 135, 40, 1];
          }
        }
        const bg = rgba(style.backgroundColor);
        if (bg && bg[3] > 0) return bg;
        node = node.parentElement;
      }
      return rgba(getComputedStyle(document.body).backgroundColor) || [19, 19, 19, 1];
    };
    const lowContrast = [...document.querySelectorAll("body, body *")]
      .filter(visible)
      .filter((el) => {
        const text = (el.innerText || el.textContent || "").trim();
        return text && !["SCRIPT", "STYLE"].includes(el.tagName);
      })
      .map((el) => {
        const style = getComputedStyle(el);
        const color = rgba(style.color);
        const ratio = color ? contrast(color, backgroundFor(el)) : 21;
        const fontSize = Number.parseFloat(style.fontSize);
        const required = fontSize >= 18 ? 3 : 4.5;
        return { selector: selectorName(el), ratio, required };
      })
      .filter((item) => item.ratio < item.required)
      .slice(0, 12);
    if (lowContrast.length) {
      failures.push(`text contrast below WCAG AA: ${lowContrast.map((item) => `${item.selector} ${item.ratio.toFixed(2)}<${item.required}`).join("; ")}`);
    }

    const width = document.documentElement.clientWidth;
    const overflow = [...document.querySelectorAll("body *")]
      .filter(visible)
      .filter((el) => {
        const box = el.getBoundingClientRect();
        return box.left < -1 || box.right > width + 1;
      })
      .slice(0, 10)
      .map(selectorName);
    if (overflow.length) failures.push(`horizontal overflow: ${overflow.join(", ")}`);

    notes.push(`${controls.length} visible interactive controls have accessible names.`);
    notes.push(`${tabs.length} tabs use role=tab with a single selected tab.`);
    return { failures, notes };
  });

  await page.keyboard.press("Tab");
  const focusEvidence = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return { ok: false, selector: "none", outline: "none" };
    const style = getComputedStyle(active);
    return {
      ok: style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) >= 2,
      selector: `${active.tagName.toLowerCase()}#${active.id || ""}.${[...active.classList].join(".")}`,
      outline: `${style.outlineWidth} ${style.outlineStyle} ${style.outlineColor}`,
    };
  });
  if (!focusEvidence.ok) {
    result.failures.push(`keyboard focus indicator missing after Tab: ${focusEvidence.selector}`);
  }
  result.notes.push(`first Tab focus: ${focusEvidence.selector} (${focusEvidence.outline})`);

  await page.close();
  return { name, viewport, ...result };
}

(async () => {
  ensureDir(uxDir);
  const browser = await chromium.launch({ headless: true });
  const server = await startServer();
  let audits;
  try {
    audits = [
      await auditViewport(browser, "desktop", { width: 1440, height: 1000 }),
      await auditViewport(browser, "laptop", { width: 1280, height: 800 }),
      await auditViewport(browser, "tablet", { width: 768, height: 1024 }),
      await auditViewport(browser, "mobile", { width: 390, height: 844 }),
    ];
  } finally {
    await browser.close();
    server.kill();
  }

  const failures = audits.flatMap((audit) => audit.failures.map((failure) => `${audit.name}: ${failure}`));
  const status = failures.length ? "fail" : "pass";
  const jsonPath = path.join(uxDir, "accessibility-audit.json");
  const mdPath = path.join(uxDir, "accessibility-audit.md");
  const report = { status, audits };
  fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2) + "\n");
  fs.writeFileSync(mdPath, [
    "# Accessibility Audit Evidence",
    "",
    `Status: ${status}.`,
    "",
    "Checked:",
    "",
    "- Desktop, laptop, tablet, and mobile landmarks.",
    "- Accessible names for visible interactive controls.",
    "- One H1 and labelled replay/tabs/range widgets.",
    "- WCAG AA text contrast for rendered visible text.",
    "- Keyboard focus indicator after Tab.",
    "- No horizontal overflow in checked viewports.",
    "",
    "Evidence:",
    "",
    `- ${rel(jsonPath)}`,
    "",
    "Viewport notes:",
    "",
    ...audits.flatMap((audit) => [`- ${audit.name}: ${audit.notes.join(" ")}`]),
    "",
    failures.length ? "Failures:" : "Failures: none.",
    "",
    ...failures.map((failure) => `- ${failure}`),
    "",
  ].join("\n"));

  console.log(JSON.stringify({ status, evidence: [rel(jsonPath), rel(mdPath)], failures }, null, 2));
  if (failures.length) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
