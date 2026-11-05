// Tight crop of the export block for before/after comparison.
const puppeteer = require("C:/Users/Administrator/.dsh/profiles/desktop/node_modules/puppeteer-core");
const DIR = "D:/Harness/dsh/workspace/cfp-assistant/docs/screenshots";

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: "new",
    args: ["--no-sandbox", "--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });
  await page.goto("http://127.0.0.1:8770/", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector("#year-calendar .cal-month", { timeout: 20000 });
  await page.click("#btn-settings");
  await page.waitForFunction(() => !document.querySelector("#settings").hidden, { timeout: 8000 });
  await new Promise((r) => setTimeout(r, 500));
  await page.evaluate(() => {
    const head = [...document.querySelectorAll("#settings h3")].find((h) => h.textContent.includes("导出"));
    if (head) head.scrollIntoView({ block: "center" });
  });
  await new Promise((r) => setTimeout(r, 400));

  const rect = await page.evaluate(() => {
    const head = [...document.querySelectorAll("#settings h3")].find((h) => h.textContent.includes("导出"));
    const hint = head.nextElementSibling.nextElementSibling;
    const top = head.getBoundingClientRect().top - 12;
    const bottom = hint.getBoundingClientRect().bottom + 12;
    const drawer = document.querySelector("#settings").getBoundingClientRect();
    return { x: Math.round(drawer.left + 16), y: Math.round(top), width: Math.round(drawer.width - 32), height: Math.round(bottom - top) };
  });
  await page.screenshot({ path: `${DIR}/settings-export.png`, clip: rect });
  console.log(JSON.stringify(rect));
  await browser.close();
})().catch((err) => { console.error("FAILED:", err.message); process.exit(1); });
