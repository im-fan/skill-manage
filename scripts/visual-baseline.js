const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const repoRoot = path.join(__dirname, "..");
const htmlUrl = pathToFileURL(path.join(repoRoot, "web", "skill-manage.html")).href;
const outDir = path.join(repoRoot, "visual-baseline");
const chromeCandidates = [
  process.env.CHROME_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "google-chrome",
  "chromium",
  "chromium-browser"
].filter(Boolean);

const chrome = chromeCandidates.find((candidate) => {
  if (candidate.includes("/") && fs.existsSync(candidate)) return true;
  const result = spawnSync("which", [candidate], { encoding: "utf8" });
  return result.status === 0;
});

if (!chrome) {
  console.error("Chrome/Chromium not found. Set CHROME_BIN to run visual baselines.");
  process.exit(1);
}

fs.mkdirSync(outDir, { recursive: true });

const desktopTabs = ["overview", "local", "agent-list", "system"];
const shots = desktopTabs.flatMap((tab) => [
  { name: `1366x768-light-${tab}.png`, size: "1366,768", query: `tab=${tab}&theme=light` },
  { name: `1366x768-dark-${tab}.png`, size: "1366,768", query: `tab=${tab}&theme=dark` }
]);

shots.push(
  { name: "390x844-light-system.png", size: "390,844", query: "tab=system&theme=light" },
  { name: "390x844-light-skill-detail.png", size: "390,844", query: "tab=local&theme=light&visual=skill-detail" }
);

for (const shot of shots) {
  const [shotWidth] = shot.size.split(",");
  const visualQuery = shotWidth === "390" ? `${shot.query}&visual-width=390` : shot.query;
  const checkResult = spawnSync(chrome, [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--virtual-time-budget=2000",
    `--window-size=${shot.size}`,
    "--dump-dom",
    `${htmlUrl}?${visualQuery}&layout-check=1`
  ], { encoding: "utf8", maxBuffer: 1024 * 1024 * 5 });

  if (checkResult.status !== 0) {
    console.error(checkResult.stderr || checkResult.stdout || `Layout check failed: ${shot.name}`);
    process.exit(checkResult.status || 1);
  }

  const match = checkResult.stdout.match(/<meta name="visual-layout-check" content="([^"]+)"/);
  const layoutResult = match?.[1] || "";
  if (layoutResult !== "ok") {
    const detail = layoutResult.startsWith("fail:")
      ? decodeURIComponent(layoutResult.slice("fail:".length))
      : "missing visual-layout-check marker";
    console.error(`Layout overflow in ${shot.name}: ${detail}`);
    process.exit(1);
  }

  const target = path.join(outDir, shot.name);
  const result = spawnSync(chrome, [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--virtual-time-budget=2000",
    `--window-size=${shot.size}`,
    `--screenshot=${target}`,
    `${htmlUrl}?${visualQuery}`
  ], { encoding: "utf8" });

  if (result.status !== 0) {
    console.error(result.stderr || result.stdout || `Screenshot failed: ${shot.name}`);
    process.exit(result.status || 1);
  }
}

console.log(`Wrote ${shots.length} screenshots to ${path.relative(repoRoot, outDir)}`);
