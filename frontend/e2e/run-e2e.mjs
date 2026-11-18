// End-to-end test of the web application against the real FastAPI backend.
// Usage: node e2e/run-e2e.mjs   (starts backend/tests/e2e_server.py itself)
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");
const PORT = 8899;
const BASE = `http://127.0.0.1:${PORT}`;
const shots = process.env.E2E_SHOTS || join(repo, "frontend", "test-results");
mkdirSync(shots, { recursive: true });
const dataDir = mkdtempSync(join(tmpdir(), "fbo-e2e-"));
const server = spawn(process.env.PYTHON || "python3", [join(repo, "backend", "tests", "e2e_server.py"), dataDir, String(PORT)], { stdio: "inherit" });

let failures = 0;
const results = [];
async function step(name, fn) {
  try {
    await fn();
    results.push(`PASS  ${name}`);
  } catch (e) {
    failures++;
    results.push(`FAIL  ${name}: ${e.message.split("\n")[0]}`);
  }
}
const assert = (c, m) => { if (!c) throw new Error(m); };
// Polls from the test side (no in-page eval: the app's CSP forbids 'unsafe-eval', as it should).
async function poll(fn, msg, tries = 50) {
  for (let i = 0; i < tries; i++) { if (await fn()) return; await new Promise((r) => setTimeout(r, 200)); }
  throw new Error(msg);
}

async function waitHealth() {
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(`${BASE}/api/health`)).ok) return; } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("backend did not start");
}

try {
  await waitHealth();
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 860 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error" && !/\b(401|422)\b/.test(m.text())) consoleErrors.push(m.text()); }); // 401/422 are triggered on purpose

  await step("first-run setup creates admin (Arabic RTL default)", async () => {
    await page.goto(BASE);
    await page.getByText("الإعداد الأولي").waitFor();
    assert((await page.getAttribute("html", "dir")) === "rtl", "html dir should be rtl");
    await page.locator("input").nth(0).fill("مدير النظام");
    await page.locator("input[name=username]").fill("admin");
    await page.locator("input[name=password]").fill("Str0ngPassw0rd!");
    await page.getByRole("button", { name: "إنشاء حساب المدير" }).click();
    await page.getByRole("heading", { name: "لوحة التحقيقات" }).waitFor();
    await page.screenshot({ path: join(shots, "01-dashboard-ar.png") });
  });

  await step("settings: store Meta token (encrypted) and see masked value", async () => {
    await page.getByTestId("nav-settings").click();
    await page.getByRole("heading", { name: "بيانات اعتماد Meta Graph API" }).waitFor();
    const tokenInput = page.locator('input[type=password]').nth(1);
    await tokenInput.fill("EAAGtesttoken1234567890");
    await page.getByRole("button", { name: "حفظ" }).nth(1).click();
    await page.getByText("EAAG••••7890").waitFor();
  });

  let invUrl = "";
  await step("new investigation of a Facebook Page runs to completion", async () => {
    await page.getByTestId("nav-new").click();
    await page.locator("input[name=target]").fill("https://www.facebook.com/qusoorfacades");
    await page.locator("select[name=target_type]").selectOption("page_url");
    await page.locator("textarea[name=purpose]").fill("تقييم مورد واجهات قبل التعاقد");
    await page.locator("textarea[name=extra_urls]").fill("https://directory.example.org/qusoor");
    await page.getByTestId("start").click();
    await page.waitForURL(/\/investigations\/\d+\/profile/);
    invUrl = page.url().replace(/\/profile$/, "");
    await page.getByText("مكتمل").first().waitFor({ timeout: 20000 });
    await page.getByText("Qusoor Facades Co.").first().waitFor();
    await page.screenshot({ path: join(shots, "02-profile-ar.png"), fullPage: true });
  });

  await step("contacts tab shows sourced public contacts", async () => {
    await page.getByTestId("nav-contacts").click();
    await page.getByText("sales@qusoor.example.sa").first().waitFor();
    assert(await page.getByText("https://directory.example.org/qusoor").count() > 0, "source URL shown");
  });

  await step("posts: keyword search + timeline", async () => {
    await page.getByTestId("nav-posts").click();
    await page.getByText("Skylight delivered").waitFor();
    await page.getByTestId("posts-search").fill("glazing");
    await page.getByTestId("posts-search").press("Enter");
    await poll(async () => (await page.locator(".post").count()) === 1, "search did not filter posts");
    assert(await page.getByText("Structural glazing installation").isVisible(), "filtered post visible");
  });

  await step("media: collected images displayed, duplicate group flagged, upload works", async () => {
    await page.getByTestId("nav-media").click();
    await page.locator(".media-card img").first().waitFor();
    const srcs = await page.locator(".media-card img").evaluateAll((imgs) => imgs.map((i) => i.getAttribute("src")));
    for (const src of srcs) {
      const r = await page.request.get(BASE + src);
      assert(r.ok() && r.headers()["content-type"].startsWith("image/"), `image ${src} not served`);
    }
    await page.locator(".media-card img").first().evaluate((i) => i.decode());
    assert(await page.locator(".media-card.dup").count() >= 2, "duplicate group highlighted");
    // valid 8x8 PNG
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGM8ISfHgA0wYRUdtBIA0MoBFD5jqJkAAAAASUVORK5CYII=", "base64");
    const before = await page.locator(".media-card").count();
    await page.getByTestId("media-file").setInputFiles({ name: "evidence.png", mimeType: "image/png", buffer: png });
    await page.getByRole("button", { name: "إضافة", exact: true }).click();
    for (let i = 0; i < 50 && (await page.locator(".media-card").count()) !== before + 1; i++) await page.waitForTimeout(200);
    assert((await page.locator(".media-card").count()) === before + 1, "uploaded image not shown");
    await page.screenshot({ path: join(shots, "06-media-ar.png"), fullPage: true });
  });

  await step("source verification lists sources and statuses", async () => {
    await page.getByTestId("nav-sources").click();
    await page.getByText("https://graph.facebook.com/v23.0/qusoorfacades").waitFor();
    assert(await page.getByText("تم الجلب").count() >= 3, "fetched badges");
    await page.screenshot({ path: join(shots, "03-sources-ar.png"), fullPage: true });
  });

  for (const fmt of ["pdf", "xlsx"]) {
    await step(`export ${fmt} downloads a valid file`, async () => {
      await page.getByTestId("nav-export").click();
      const [dl] = await Promise.all([page.waitForEvent("download"), page.getByTestId(`export-${fmt}`).click()]);
      const p = await dl.path();
      const head = readFileSync(p).subarray(0, 4).toString("latin1");
      assert(fmt === "pdf" ? head === "%PDF" : head.startsWith("PK"), `bad ${fmt} signature ${head}`);
      assert(dl.suggestedFilename().startsWith("INV-"), "filename has reference");
    });
  }

  await step("manual observation can be added and reviewed", async () => {
    await page.goto(`${invUrl}/profile`);
    await page.getByText("إضافة ملاحظة يدوية").first().click();
    const form = page.locator("details.manual form").first();
    await form.locator("input").nth(0).fill("workplace");
    await form.locator("input").nth(1).fill("Qusoor Al Sultan Industry (listed on company site)");
    await form.locator("input").nth(2).fill("https://qusoor.example.sa/team");
    await form.getByRole("button", { name: "إضافة" }).click();
    await page.getByText("Qusoor Al Sultan Industry (listed on company site)").waitFor();
  });

  await step("language switch to English LTR", async () => {
    await page.getByTestId("lang-toggle").click();
    assert((await page.getAttribute("html", "dir")) === "ltr", "dir ltr");
    await page.getByText("Available information").waitFor();
    await page.screenshot({ path: join(shots, "04-profile-en.png"), fullPage: true });
    await page.getByTestId("lang-toggle").click();
  });

  await step("invalid target rejected with message", async () => {
    await page.getByTestId("nav-new").click();
    await page.locator("input[name=target]").fill("https://evil.example.com/someone");
    await page.locator("textarea[name=purpose]").fill("اختبار رابط غير صالح");
    await page.getByTestId("start").click();
    await page.getByText("الهدف ليس رابط ملف").waitFor();
  });

  await step("private personal profile -> partial with limitation", async () => {
    await page.locator("input[name=target]").fill("https://www.facebook.com/john.doe.123");
    await page.locator("select[name=target_type]").selectOption("auto");
    await page.getByTestId("start").click();
    await page.waitForURL(/\/profile$/);
    await page.getByText("graph_not_found").first().waitFor({ timeout: 20000 });
    await page.getByText("جزئي").first().waitFor();
  });

  await step("history search finds investigations", async () => {
    await page.getByTestId("nav-history").click();
    await page.getByTestId("history-search").fill("qusoor");
    await page.getByTestId("history-search").press("Enter");
    await poll(async () => (await page.locator("tbody tr").count()) === 1, "history search did not filter");
  });

  await step("responsive mobile layout has no horizontal overflow", async () => {
    const m = await browser.newContext({ viewport: { width: 390, height: 844 }, storageState: await ctx.storageState() });
    const mp = await m.newPage();
    await mp.goto(`${invUrl}/contacts`);
    await mp.getByText("sales@qusoor.example.sa").first().waitFor();
    const overflow = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(overflow <= 1, `page overflows by ${overflow}px`);
    await mp.screenshot({ path: join(shots, "05-mobile-ar.png") });
    await m.close();
  });

  await step("logout ends the session", async () => {
    await page.getByTestId("logout").click();
    await page.getByRole("button", { name: "دخول" }).waitFor();
    const r = await page.request.get(`${BASE}/api/auth/me`);
    assert(r.status() === 401, "session revoked");
  });

  await step("no unexpected console errors", async () => assert(consoleErrors.length === 0, consoleErrors.join(" | ")));
  await browser.close();
} catch (e) {
  failures++;
  results.push(`FAIL  harness: ${e.message}`);
} finally {
  server.kill();
}
console.log("\n" + results.join("\n"));
console.log(`\n${results.length - failures} passed, ${failures} failed`);
writeFileSync(join(shots, "e2e-results.txt"), results.join("\n"));
process.exit(failures ? 1 : 0);
