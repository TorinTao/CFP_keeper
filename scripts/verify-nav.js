// Verifies the top navigation: three views, hash sync, and screenshots.
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

  await page.goto("http://127.0.0.1:8770/", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector("#rows tr", { timeout: 20000 });

  const read = () =>
    page.evaluate(() => ({
      tabs: Array.from(document.querySelectorAll(".nav-tab")).map((b) => ({
        label: b.textContent.trim(),
        active: b.classList.contains("active"),
      })),
      calendarVisible: !document.querySelector("#view-calendar").hidden,
      allVisible: !document.querySelector("#view-all").hidden,
      watchVisible: !document.querySelector("#view-watch").hidden,
      hash: location.hash,
      navCountdown: document.querySelector("#nav-countdown").textContent,
      allRows: document.querySelectorAll("#rows tr").length,
      watchRows: document.querySelectorAll("#rows-home tr").length,
    }));

  const initial = await read();
  await page.screenshot({ path: `${DIR}/nav-calendar.png` });

  await page.click('.nav-tab[data-view="all"]');
  await new Promise((r) => setTimeout(r, 500));
  const allView = await read();
  await page.screenshot({ path: `${DIR}/nav-all.png` });

  await page.click('.nav-tab[data-view="watch"]');
  await new Promise((r) => setTimeout(r, 500));
  const watchView = await read();
  await page.screenshot({ path: `${DIR}/nav-watch.png` });

  // deep link: reload with #all
  await page.goto("http://127.0.0.1:8770/#all", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector("#rows tr", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 400));
  const deepLink = await read();

  console.log(JSON.stringify({ initial, allView, watchView, deepLink, errors }, null, 2));
  await browser.close();
})().catch((err) => {
  console.error("FAILED:", err.message);
  process.exit(1);
});
