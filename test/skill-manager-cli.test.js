const assert = require("node:assert/strict");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
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

function makeFakePython(home) {
  const fakePython = path.join(home, "fake-python.js");
  fs.writeFileSync(fakePython, `#!/usr/bin/env node
if (process.argv[2] === "-c") process.exit(0);
setInterval(() => {}, 1000);
`);
  fs.chmodSync(fakePython, 0o755);
  return fakePython;
}

function spawnPortOwner() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [
      "-e",
      `
const net = require("node:net");
const server = net.createServer();
server.listen(0, "127.0.0.1", () => {
  console.log(server.address().port);
});
setInterval(() => {}, 1000);
`,
    ], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
      const port = Number(output.trim());
      if (Number.isInteger(port) && port > 0) {
        resolve({ child, port });
      }
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      reject(new Error(`port owner exited before listening: ${code}`));
    });
  });
}

function findFreePort() {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function killIfAlive(pid) {
  if (!pid) return;
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Already gone.
  }
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

test("start kills a process occupying the configured port and continues startup", async () => {
  const { child: portOwner, port } = await spawnPortOwner();
  let startedPid = null;

  try {
    const home = makeTempHome();
    fs.writeFileSync(path.join(home, "config.json"), JSON.stringify({
      server: { host: "127.0.0.1", port },
      runtimeHome: home,
    }));
    const fakePython = makeFakePython(home);

    const result = runCli(["start"], { SKILL_MANAGER_HOME: home, SKILL_MANAGER_PYTHON: fakePython });

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, new RegExp(`killed process ${portOwner.pid} occupying port ${port}`));
    assert.match(result.stdout, /skill-manager started/);
    assert.equal(portOwner.exitCode, null);

    await new Promise((resolve) => portOwner.once("exit", resolve));
    const state = JSON.parse(fs.readFileSync(path.join(home, "run", "skill-manager.json"), "utf8"));
    startedPid = state.pid;
    assert.notEqual(startedPid, portOwner.pid);
  } finally {
    killIfAlive(portOwner.pid);
    killIfAlive(startedPid);
  }
});

test("start restarts an already running managed service", async () => {
  const home = makeTempHome();
  const port = await findFreePort();
  let firstPid = null;
  let secondPid = null;
  fs.writeFileSync(path.join(home, "config.json"), JSON.stringify({
    server: { host: "127.0.0.1", port },
    runtimeHome: home,
  }));
  const fakePython = makeFakePython(home);

  try {
    const first = runCli(["start"], { SKILL_MANAGER_HOME: home, SKILL_MANAGER_PYTHON: fakePython });
    assert.equal(first.status, 0, first.stderr);
    firstPid = JSON.parse(fs.readFileSync(path.join(home, "run", "skill-manager.json"), "utf8")).pid;

    const second = runCli(["start"], { SKILL_MANAGER_HOME: home, SKILL_MANAGER_PYTHON: fakePython });

    assert.equal(second.status, 0, second.stderr);
    assert.match(second.stdout, /skill-manager restarted/);
    secondPid = JSON.parse(fs.readFileSync(path.join(home, "run", "skill-manager.json"), "utf8")).pid;
    assert.notEqual(secondPid, firstPid);
    assert.throws(() => process.kill(firstPid, 0));
  } finally {
    killIfAlive(firstPid);
    killIfAlive(secondPid);
  }
});
