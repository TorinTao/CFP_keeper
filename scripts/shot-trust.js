// Desktop + mobile screenshots after the trust/visibility changes.
const puppeteer = require("C:/Users/Administrator/.dsh/profiles/desktop/node_modules/puppeteer-core");
const DIR = "D:/Harness/dsh/workspace/cfp-assistant/docs/screenshots";

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: "new",
    args: ["--no-sandbox", "--hide-scrollbars"],
  });
  const errors = [];

  // desktop list
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("http://127.0.0.1:8770/#all", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll("#rows tr").length > 5, { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 600));
  const desktop = await page.evaluate(() => {
    const row = document.querySelector("#rows tr.row");
    return {
      checked: !!row.querySelector(".checked-at"),
      checkedText: (row.querySelector(".checked-at") || {}).textContent || "",
      disputed: document.querySelectorAll("#rows .badge.disputed").length,
    };
  });
  await page.screenshot({ path: `${DIR}/list-trust.png` });

  // mobile
  const mob = await browser.newPage();
  await mob.setViewport({ width: 390, height: 844 });
  mob.on("pageerror", (e) => errors.push(String(e)));
  await mob.goto("http://127.0.0.1:8770/#all", { waitUntil: "networkidle2", timeout: 30000 });
  await mob.waitForFunction(() => document.querySelectorAll("#rows tr").length > 3, { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 600));
  const mobile = await mob.evaluate(() => ({
    docW: document.documentElement.scrollWidth,
    winW: window.innerWidth,
    overflow: document.documentElement.scrollWidth > window.innerWidth,
  }));
  await mob.screenshot({ path: `${DIR}/mobile-fixed.png` });

  console.log(JSON.stringify({ desktop, mobile, errors }, null, 1));
  await browser.close();
})().catch((err) => { console.error("FAILED:", err.message); process.exit(1); });
