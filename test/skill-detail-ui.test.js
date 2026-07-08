const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const repoRoot = path.join(__dirname, "..");
const htmlPath = path.join(repoRoot, "web", "skill-manage.html");

test("skill detail dialog exposes file tree, readonly preview, and copy action", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /id="skillDetailTree"/);
  assert.match(html, /id="skillDetailPreview"/);
  assert.match(html, /readonly/);
  assert.match(html, /data-action="copy-skill-file"/);
  assert.match(html, /\/api\/skill-detail\?path=/);
});

test("skill detail dialog shows the real skill path and locks page scroll while open", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /id="skillDetailPath"/);
  assert.match(html, /detail\.path\s*\|\|\s*detail\.target_path/);
  assert.match(html, /document\.body\.classList\.add\("modal-open"\)/);
  assert.match(html, /document\.body\.classList\.remove\("modal-open"\)/);
  assert.match(html, /body\.modal-open/);
});

test("skill detail dialog has fixed dimensions and copy success feedback", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /#skillDetailDialog\s*{[^}]*width:\s*min\(1040px,\s*calc\(100vw - 32px\)\)/s);
  assert.match(html, /#skillDetailDialog\s*{[^}]*height:\s*min\(720px,\s*calc\(100dvh - 32px\)\)/s);
  assert.match(html, /#skillDetailCopyStatus/);
  assert.match(html, /dialog\.skillDetail\.copySuccess/);
  assert.match(html, /setSkillDetailCopyStatus\(t\("dialog\.skillDetail\.copySuccess"\),\s*{\s*autoHide:\s*true\s*}\)/);
});

test("skill detail copy feedback is left of right-aligned button and auto-hides", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /\.skill-detail-copy-actions\s*{[^}]*margin-left:\s*auto/s);
  assert.match(html, /<div class="skill-detail-copy-actions">\s*<span id="skillDetailCopyStatus"[\s\S]*?<button id="skillDetailCopy"/);
  assert.match(html, /let skillDetailCopyStatusTimer\s*=\s*null/);
  assert.match(html, /setTimeout\(\(\)\s*=>\s*{\s*setSkillDetailCopyStatus\(""\);\s*},\s*2000\)/s);
});

test("git scan root card title prefers note then git project name", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /function scanRootDisplayName\(root\)/);
  assert.match(html, /String\(root\.note \|\| ""\)\.trim\(\) \|\| gitProjectName\(root\.git_url\) \|\| pathLeafName\(root\.path\)/);
  assert.match(html, /<strong>\$\{escapeHtml\(scanRootDisplayName\(root\)\)\}<\/strong>/);
});

test("workbench uses left navigation, breadcrumb, and agent tabs in content", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /<nav class="side-nav" aria-label="Primary">/);
  assert.match(html, /id="breadcrumb" class="breadcrumb"/);
  assert.match(html, /id="agentTabs" class="agent-tabs" role="tablist"/);
  assert.match(html, /\["overview", t\("tab\.overview"\)\]/);
  assert.doesNotMatch(html, new RegExp(`tab\\.${["market", "place"].join("")}`));
});

test("removed product surface stays out of the frontend", () => {
  const html = fs.readFileSync(htmlPath, "utf8");
  const removedName = ["market", "place"].join("");
  const removedTitle = `${removedName[0].toUpperCase()}${removedName.slice(1)}`;
  const removedCapabilityApi = ["agent", "capabilities"].join("-");
  const removedCapabilityState = ["agent", "Capabilities"].join("");

  assert.doesNotMatch(html, new RegExp(`id="tab-${removedName}"`));
  assert.doesNotMatch(html, new RegExp(`${removedName}|${removedTitle}|${removedCapabilityApi}|${removedCapabilityState}|${removedName}AgentFilter`));
  assert.doesNotMatch(html, /\/api\/plugins\/(install|update|uninstall)/);
  assert.doesNotMatch(html, /pluginPreview/);
});

test("system tab removes the recent operations UI and inert log rendering code", () => {
  const html = fs.readFileSync(htmlPath, "utf8");
  const logDomId = ["operation", "Log"].join("");
  const logStateKey = ["operation", "Logs"].join("");
  const logApi = ["/api/operation", "logs"].join("-");

  assert.doesNotMatch(html, new RegExp(`id="${logDomId}"`));
  assert.doesNotMatch(html, />最近操作</);
  assert.doesNotMatch(html, /function renderLogs\(\)/);
  assert.doesNotMatch(html, new RegExp(logStateKey));
  assert.doesNotMatch(html, new RegExp(logApi));
});

test("system tab only renders the approved system fields", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /\.system-layout\s*{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(html, /\.system-status-grid\s*{[^}]*repeat\(auto-fit,\s*minmax\(240px,\s*1fr\)\)/s);
  assert.match(html, /common\.serviceStatus/);
  assert.match(html, /common\.serviceUrl/);
  assert.match(html, /common\.sqlite/);
  assert.match(html, /common\.configPath/);
  assert.doesNotMatch(html, /common\.python/);
  assert.doesNotMatch(html, /common\.agentCount/);
  assert.doesNotMatch(html, /common\.localSkillCount/);
  assert.doesNotMatch(html, /common\.invalidSkillCount/);
});

test("visual polish keeps motion and token gates in scope", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /--radius:\s*12px/);
  assert.match(html, /--radius-sm:\s*8px/);
  assert.match(html, /--radius-md:\s*12px/);
  assert.match(html, /--radius-lg:\s*16px/);
  assert.match(html, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(html, /transition-duration:\s*0\.01ms\s*!important/);
  assert.match(html, /transform:\s*scale\(1\.01\)/);
  assert.doesNotMatch(html, /transform:\s*scale\(1\.(0[3-9]|[1-9]\d)\)/);
  assert.doesNotMatch(html, /🗃️ Skill Manage/);
});

test("visual baseline mode can target tab, theme, and skill detail dialog", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /const params = new URLSearchParams\(location\.search\)/);
  assert.match(html, /activeTab:\s*params\.get\("tab"\)\s*\|\|\s*"overview"/);
  assert.match(html, /function setActiveTab\(tab\)/);
  assert.match(html, /params\.set\("tab", tab\)/);
  assert.match(html, /history\.replaceState\(null,\s*"",\s*`\$\{location\.pathname\}\?\$\{params\.toString\(\)\}\$\{location\.hash\}`\)/);
  assert.match(html, /if \(target\.dataset\.tab\) {\s*setActiveTab\(target\.dataset\.tab\)/);
  assert.match(html, /if \(action === "select-agent"\) {[\s\S]*?setActiveTab\("agent-list"\)/);
  assert.match(html, /if \(action === "edit-agent"\) {[\s\S]*?setActiveTab\("agent-manage"\)/);
  assert.match(html, /theme:\s*params\.get\("theme"\)\s*\|\|/);
  assert.match(html, /function applyVisualBaselineMode\(\)/);
  assert.match(html, /visualMode !== "skill-detail"/);
  assert.match(html, /dialog\.showModal\(\)/);
});

test("mobile visual baselines avoid horizontal clipping", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  assert.match(html, /@media\s*\(max-width:\s*720px\)\s*{[\s\S]*?\.shell\s*{[^}]*width:\s*100%/s);
  assert.match(html, /@media\s*\(max-width:\s*720px\)\s*{[\s\S]*?\.side-nav-list\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(html, /\.empty\s*{[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(html, /\.empty\s*{[^}]*word-break:\s*break-word/s);
  assert.match(html, /@media\s*\(max-width:\s*720px\)\s*{[\s\S]*?\.panel-grid\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(html, /@media\s*\(max-width:\s*720px\)\s*{[\s\S]*?#skillDetailDialog\s*{[^}]*width:\s*calc\(100vw - 40px\)/s);
  assert.match(html, /dialog\s*{[^}]*max-width:\s*calc\(100vw - 32px\)/s);
  assert.match(html, /function applyVisualLayoutCheck\(\)/);
  assert.match(html, /params\.get\("layout-check"\) !== "1"/);
  assert.match(html, /visualWidth === "390"/);
  assert.match(html, /html\[data-visual-width="390"\] \.shell/);
  assert.match(html, /html\[data-visual-width="390"\] #skillDetailDialog/);
  assert.match(html, /document\.documentElement\.scrollWidth/);
  assert.match(html, /const layoutViewportWidth = window\.innerWidth/);
  assert.match(html, /const captureWidth = Number\(params\.get\("visual-width"\)\) \|\| layoutViewportWidth/);
  assert.match(html, /visual-layout-check/);
});
