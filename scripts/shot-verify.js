// Screenshots for the verification feature: nav button, status badges, drawer.
const puppeteer = require("C:/Users/Administrator/.dsh/profiles/desktop/node_modules/puppeteer-core");

const DIR = "D:/Harness/dsh/workspace/cfp-assistant/docs/screenshots";

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("http://127.0.0.1:8770/#all", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector("#rows tr", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 600));

  const badges = await page.evaluate(() => {
    const out = {};
    document.querySelectorAll("#rows .badge").forEach((b) => {
      out[b.textContent.trim()] = (out[b.textContent.trim()] || 0) + 1;
    });
    return out;
  });
  await page.screenshot({ path: `${DIR}/verify-all.png` });

  // open CVPR drawer (confirmed + verified rows)
  await page.evaluate(() => {
    const row = Array.from(document.querySelectorAll("#rows tr")).find((r) => r.innerText.includes("CVPR"));
    if (row) row.click();
  });
  await page.waitForSelector("#drawer:not([hidden])", { timeout: 8000 });
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({ path: `${DIR}/verify-drawer.png` });

  // settings section for verification
  await page.evaluate(() => {
    document.querySelector("#drawer").hidden = true;
    document.querySelector("#overlay").hidden = true;
  });
  await page.click("#btn-settings");
  await page.waitForSelector("#settings:not([hidden])", { timeout: 5000 });
  await new Promise((r) => setTimeout(r, 500));
  await page.evaluate(() => {
    const head = Array.from(document.querySelectorAll("#settings h3")).find((h) => h.textContent.includes("自动核验"));
    if (head) head.scrollIntoView({ block: "center" });
  });
  await new Promise((r) => setTimeout(r, 300));
  const verifyInfo = await page.evaluate(() => document.querySelector("#s-verify-info").textContent.trim());
  await page.screenshot({ path: `${DIR}/verify-settings.png` });

  console.log(JSON.stringify({ badges, verifyInfo, errors }, null, 2));
  await browser.close();
})().catch((err) => {
  console.error("FAILED:", err.message);
  process.exit(1);
});
