const assert = require("node:assert/strict");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const repoRoot = path.resolve(__dirname, "..");
const cliPath = path.join(repoRoot, "bin", "skill-manager.js");

function makeTempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "skill-manager-cli-"));
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function runCli(args, env = {}) {
  return spawnSync(process.execPath, [cliPath, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      SKILL_MANAGER_HOME: makeTempHome(),
      SKILL_MANAGE_HOME: "",
      SKILL_MANAGER_CONFIG: "",
      ...env,
    },
    encoding: "utf8",
  });
}

test("prints help and package version", () => {
  const help = runCli(["h"]);
  assert.equal(help.status, 0);
  assert.match(help.stdout, /skill-manager start/);
  assert.match(help.stdout, /status/);

  const version = runCli(["version"]);
  const packageJson = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  assert.equal(version.status, 0);
  assert.match(version.stdout, new RegExp(escapeRegExp(packageJson.version)));
});

test("status initializes config and reports stopped when no pid exists", () => {
  const home = makeTempHome();
  const result = runCli(["status"], { SKILL_MANAGER_HOME: home });

  assert.equal(result.status, 0);
  assert.match(result.stdout, /stopped/i);
  assert.match(result.stdout, new RegExp(escapeRegExp(path.join(home, "config.json"))));

  const config = JSON.parse(fs.readFileSync(path.join(home, "config.json"), "utf8"));
  assert.deepEqual(config.server, { host: "127.0.0.1", port: 8765 });
  assert.equal(config.runtimeHome, home);
});

test("status reports stale pid without claiming the service is running", () => {
  const home = makeTempHome();
  const runDir = path.join(home, "run");
  fs.mkdirSync(runDir, { recursive: true });
  fs.writeFileSync(path.join(home, "config.json"), JSON.stringify({
    server: { host: "127.0.0.1", port: 8765 },
    runtimeHome: home,
  }));
  fs.writeFileSync(path.join(runDir, "skill-manager.pid"), "999999\n");
  fs.writeFileSync(path.join(runDir, "skill-manager.json"), JSON.stringify({
    pid: 999999,
    host: "127.0.0.1",
    port: 8765,
    url: "http://127.0.0.1:8765/",
  }));

  const result = runCli(["status"], { SKILL_MANAGER_HOME: home });

  assert.equal(result.status, 0);
  assert.match(result.stdout, /stale pid/i);
  assert.doesNotMatch(result.stdout, /^running$/im);
});

test("start refuses to kill or reuse a port owned by another process", async () => {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const home = makeTempHome();
    const port = server.address().port;
    fs.writeFileSync(path.join(home, "config.json"), JSON.stringify({
      server: { host: "127.0.0.1", port },
      runtimeHome: home,
    }));

    const result = runCli(["start"], { SKILL_MANAGER_HOME: home });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, new RegExp(`Port ${port} is already in use by another process\\.`));
    assert.match(result.stderr, new RegExp(escapeRegExp(path.join(home, "config.json"))));
    assert.match(result.stderr, /server\.port/);
  } finally {
    server.close();
  }
});
