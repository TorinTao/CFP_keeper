// Screenshots for the calendar modes and settings drawer.
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
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto("http://127.0.0.1:8770/", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector(".cal-month", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 700));

  const read = () => page.evaluate(() => ({
    dots: document.querySelectorAll(".cal-dots .dot").length,
    events: document.querySelectorAll(".cal-day.has-events").length,
    year: document.querySelector("#year-select").value,
    mode: [...document.querySelectorAll("#cal-mode .scope-tab")]
      .filter((b) => b.classList.contains("active")).map((b) => b.textContent),
  }));

  const verified = await read();
  await page.screenshot({ path: `${DIR}/calendar-verified.png` });

  await page.click('#cal-mode .scope-tab[data-mode="all"]');
  await new Promise((r) => setTimeout(r, 600));
  const all = await read();
  await page.screenshot({ path: `${DIR}/calendar-all.png` });

  await page.click("#btn-settings");
  await page.waitForFunction(() => !document.querySelector("#settings").hidden, { timeout: 8000 });
  await new Promise((r) => setTimeout(r, 600));
  const settings = await page.evaluate(() => ({
    width: Math.round(document.querySelector("#settings").getBoundingClientRect().width),
    overflow: document.querySelector("#settings .drawer-body").scrollHeight
      - document.querySelector("#settings .drawer-body").clientHeight,
    scrapeInfo: document.querySelector("#s-schedule-info").textContent.trim(),
    verifyInfo: document.querySelector("#s-verify-info").textContent.trim(),
  }));
  await page.screenshot({ path: `${DIR}/settings-now.png` });

  console.log(JSON.stringify({ verified, all, settings, errors }, null, 1));
  await browser.close();
})().catch((err) => { console.error("FAILED:", err.message); process.exit(1); });
