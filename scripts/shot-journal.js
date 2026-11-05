// Screenshots for journal verification: list row + drawer section.
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

  await page.goto("http://127.0.0.1:8770/#all", { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll("#rows tr").length > 5, { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 600));

  const rowInfo = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#rows tr.row")];
    const tmi = rows.find((r) => r.innerText.includes("IEEE Transactions on Medical Imaging"));
    if (tmi) tmi.scrollIntoView({ block: "center" });
    return tmi ? tmi.innerText.replace(/\n+/g, " | ").slice(0, 160) : null;
  });
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: `${DIR}/journal-list.png` });

  await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#rows tr.row")];
    const tmi = rows.find((r) => r.innerText.includes("IEEE Transactions on Medical Imaging"));
    if (tmi) tmi.click();
  });
  await page.waitForFunction(() => !document.querySelector("#drawer").hidden, { timeout: 8000 });
  await new Promise((r) => setTimeout(r, 600));
  const drawerInfo = await page.evaluate(() => {
    const box = document.querySelector("#d-journal");
    if (box) box.scrollIntoView({ block: "center" });
    return box && !box.hidden ? box.innerText.replace(/\n+/g, " | ").slice(0, 260) : null;
  });
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: `${DIR}/journal-drawer.png` });

  console.log(JSON.stringify({ rowInfo, drawerInfo, errors }, null, 1));
  await browser.close();
})().catch((err) => { console.error("FAILED:", err.message); process.exit(1); });
