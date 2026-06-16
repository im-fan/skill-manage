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
