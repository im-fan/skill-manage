#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const PACKAGE_JSON = require(path.join(PACKAGE_ROOT, "package.json"));
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;
const PID_FILE = "skill-manager.pid";
const STATE_FILE = "skill-manager.json";

function expandHome(value) {
  if (!value) return value;
  if (value === "~") return os.homedir();
  if (value.startsWith("~/")) return path.join(os.homedir(), value.slice(2));
  return value;
}

function resolvePath(value, baseDir = process.cwd()) {
  const expanded = expandHome(value);
  if (!expanded) return expanded;
  return path.resolve(baseDir, expanded);
}

function defaultHome() {
  return resolvePath(process.env.SKILL_MANAGER_HOME || process.env.SKILL_MANAGE_HOME || "~/.skill-manager");
}

function configPath() {
  if (process.env.SKILL_MANAGER_CONFIG) {
    return resolvePath(process.env.SKILL_MANAGER_CONFIG);
  }
  return path.join(defaultHome(), "config.json");
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function defaultConfig(home) {
  return {
    server: {
      host: DEFAULT_HOST,
      port: DEFAULT_PORT,
    },
    runtimeHome: home,
  };
}

function writeJson(filePath, value) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function loadConfig({ create = true } = {}) {
  const filePath = configPath();
  if (!fs.existsSync(filePath)) {
    if (!create) {
      throw new Error(`Config file not found: ${filePath}`);
    }
    const home = defaultHome();
    const config = defaultConfig(home);
    writeJson(filePath, config);
  }

  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error(`Invalid config JSON: ${filePath}\n${error.message}`);
  }

  const runtimeHome = resolvePath(parsed.runtimeHome || defaultHome(), path.dirname(filePath));
  const host = String(parsed.server && parsed.server.host ? parsed.server.host : DEFAULT_HOST);
  const port = Number(parsed.server && parsed.server.port ? parsed.server.port : DEFAULT_PORT);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error(`Invalid config key server.port in ${filePath}: ${parsed.server && parsed.server.port}`);
  }

  const config = {
    ...parsed,
    server: { host, port },
    runtimeHome,
  };
  return { config, path: filePath };
}

function runtimePaths(config) {
  const home = config.runtimeHome;
  return {
    home,
    dataDir: path.join(home, "data"),
    logsDir: path.join(home, "logs"),
    runDir: path.join(home, "run"),
    dbPath: path.join(home, "data", "skill-manage.sqlite3"),
    logPath: path.join(home, "logs", "skill-manage.log"),
    pidPath: path.join(home, "run", PID_FILE),
    statePath: path.join(home, "run", STATE_FILE),
  };
}

function ensureRuntimeDirs(paths) {
  ensureDir(paths.dataDir);
  ensureDir(paths.logsDir);
  ensureDir(paths.runDir);
}

function readPid(paths) {
  try {
    const raw = fs.readFileSync(paths.pidPath, "utf8").trim();
    const pid = Number(raw);
    return Number.isInteger(pid) && pid > 0 ? pid : null;
  } catch {
    return null;
  }
}

function readState(paths) {
  try {
    return JSON.parse(fs.readFileSync(paths.statePath, "utf8"));
  } catch {
    return null;
  }
}

function isProcessAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function commandForPid(pid) {
  const result = spawnSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8" });
  if (result.status !== 0) return "";
  return result.stdout.trim();
}

function isZombieProcess(pid) {
  if (process.platform === "win32") return false;
  const result = spawnSync("ps", ["-p", String(pid), "-o", "stat="], { encoding: "utf8" });
  if (result.status !== 0) return false;
  return result.stdout.trim().includes("Z");
}

function isSkillManagerProcess(pid) {
  const command = commandForPid(pid);
  return command.includes("skill_manage") || command.includes("skill-manage-server.py");
}

function pidsForPort(port) {
  const commands =
    process.platform === "win32"
      ? []
      : [
          ["lsof", ["-ti", `tcp:${port}`]],
          ["fuser", [`${port}/tcp`]],
        ];

  for (const [command, args] of commands) {
    const result = spawnSync(command, args, { encoding: "utf8" });
    if (result.error || (result.status !== 0 && !result.stdout)) continue;
    const pids = result.stdout
      .split(/\s+/)
      .map((value) => Number(value.trim()))
      .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== process.pid);
    if (pids.length > 0) return [...new Set(pids)];
  }

  return [];
}

async function killProcess(pid, label) {
  if (!isProcessAlive(pid)) return;
  process.kill(pid, "SIGTERM");
  let stopped = await waitForStop(pid, 5000);
  if (!stopped && isProcessAlive(pid)) {
    process.kill(pid, "SIGKILL");
    stopped = await waitForStop(pid, 2000);
  }
  if (isProcessAlive(pid) && !isZombieProcess(pid)) {
    throw new Error(`Failed to stop process ${pid}${label ? ` ${label}` : ""}.`);
  }
}

async function freePort(host, port) {
  if (await isPortFree(host, port)) return [];

  const killed = [];
  const pids = pidsForPort(port);
  if (pids.length === 0) {
    throw new Error(`Port ${port} is already in use, but the owning process could not be found.`);
  }

  for (const pid of pids) {
    await killProcess(pid, `occupying port ${port}`);
    killed.push(pid);
  }

  if (!(await isPortFree(host, port))) {
    throw new Error(`Port ${port} is still in use after killing process ${killed.join(", ")}.`);
  }

  return killed;
}

function getStatus(config, paths) {
  const pid = readPid(paths);
  const state = readState(paths);
  if (!pid) {
    return { state: "stopped", pid: null, storedState: state };
  }
  if (!isProcessAlive(pid)) {
    return { state: "stale pid", pid, storedState: state };
  }
  if (!isSkillManagerProcess(pid)) {
    return { state: "stale pid", pid, storedState: state };
  }
  return { state: "running", pid, storedState: state };
}

function printStatus(configInfo) {
  const { config, path: cfgPath } = configInfo;
  const paths = runtimePaths(config);
  ensureRuntimeDirs(paths);
  const status = getStatus(config, paths);
  const state = status.storedState || {};
  const url = state.url || `http://${config.server.host}:${config.server.port}/`;

  console.log(status.state);
  if (status.pid) console.log(`pid: ${status.pid}`);
  console.log(`url: ${url}`);
  console.log(`config: ${cfgPath}`);
  console.log(`log: ${paths.logPath}`);
  console.log(`database: ${paths.dbPath}`);
  console.log(`version: ${PACKAGE_JSON.version}`);
}

function checkPython(pythonBin) {
  const result = spawnSync(pythonBin, ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"], {
    encoding: "utf8",
  });
  if (result.error) {
    return false;
  }
  return result.status === 0;
}

function selectPython() {
  const configured = process.env.SKILL_MANAGER_PYTHON || process.env.SKILL_MANAGE_PYTHON;
  const candidates = configured ? [configured] : ["python3", "python"];
  for (const candidate of candidates) {
    if (checkPython(candidate)) return candidate;
  }
  const source = configured ? `configured Python executable is not usable: ${configured}` : "tried python3 and python";
  throw new Error(`Python 3.10+ is required (${source}).`);
}

function isPortFree(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

async function start() {
  const configInfo = loadConfig();
  const { config, path: cfgPath } = configInfo;
  const paths = runtimePaths(config);
  ensureRuntimeDirs(paths);
  const status = getStatus(config, paths);

  if (status.state === "running") {
    await killProcess(status.pid, "managed by skill-manager");
    cleanupRunFiles(paths);
    console.log(`skill-manager restarted from pid ${status.pid}`);
  }

  const killedPortPids = await freePort(config.server.host, config.server.port);
  for (const pid of killedPortPids) {
    console.log(`killed process ${pid} occupying port ${config.server.port}`);
  }

  const pythonBin = selectPython();

  const env = {
    ...process.env,
    SKILL_MANAGE_HOME: config.runtimeHome,
    PYTHONPATH: [path.join(PACKAGE_ROOT, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };
  const logHandle = fs.openSync(paths.logPath, "a");
  const child = spawn(pythonBin, ["-m", "skill_manage", "--host", config.server.host, "--port", String(config.server.port)], {
    cwd: PACKAGE_ROOT,
    detached: true,
    stdio: ["ignore", logHandle, logHandle],
    env,
  });
  child.unref();
  fs.closeSync(logHandle);

  const state = {
    pid: child.pid,
    host: config.server.host,
    port: config.server.port,
    url: `http://${config.server.host}:${config.server.port}/`,
    configPath: cfgPath,
    runtimeHome: config.runtimeHome,
    logPath: paths.logPath,
    dbPath: paths.dbPath,
    startedAt: new Date().toISOString(),
  };
  fs.writeFileSync(paths.pidPath, `${child.pid}\n`);
  writeJson(paths.statePath, state);

  console.log("skill-manager started");
  console.log(`pid: ${child.pid}`);
  console.log(`url: ${state.url}`);
  console.log(`log: ${paths.logPath}`);
}

async function stop({ quiet = false } = {}) {
  const configInfo = loadConfig();
  const { config } = configInfo;
  const paths = runtimePaths(config);
  ensureRuntimeDirs(paths);
  const status = getStatus(config, paths);

  if (status.state !== "running") {
    if (!quiet) console.log(status.state === "stale pid" ? "skill-manager is not running (stale pid)" : "skill-manager is not running");
    cleanupRunFiles(paths);
    return;
  }

  await killProcess(status.pid, "managed by skill-manager");
  cleanupRunFiles(paths);
  if (!quiet) console.log("skill-manager stopped");
}

function cleanupRunFiles(paths) {
  for (const filePath of [paths.pidPath, paths.statePath]) {
    try {
      fs.unlinkSync(filePath);
    } catch {
      // No cleanup needed.
    }
  }
}

function waitForStop(pid, timeoutMs) {
  const started = Date.now();
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      if (!isProcessAlive(pid)) {
        clearInterval(timer);
        resolve(true);
      } else if (isZombieProcess(pid)) {
        clearInterval(timer);
        resolve(true);
      } else if (Date.now() - started > timeoutMs) {
        clearInterval(timer);
        resolve(false);
      }
    }, 100);
  });
}

async function restart() {
  await stop({ quiet: true });
  await start();
}

function openBrowser(url) {
  const platform = process.platform;
  const command = platform === "darwin" ? "open" : platform === "win32" ? "cmd" : "xdg-open";
  const args = platform === "win32" ? ["/c", "start", "", url] : [url];
  const child = spawn(command, args, {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

function web() {
  const configInfo = loadConfig();
  const { config } = configInfo;
  const paths = runtimePaths(config);
  ensureRuntimeDirs(paths);
  const status = getStatus(config, paths);
  if (status.state !== "running") {
    throw new Error("skill-manager is not running. Run:\n  skill-manager start");
  }
  const state = status.storedState || {};
  const url = state.url || `http://${config.server.host}:${config.server.port}/`;
  openBrowser(url);
  console.log(url);
}

function help() {
  console.log(`skill-manager ${PACKAGE_JSON.version}

Usage:
  skill-manager start
  skill-manager stop
  skill-manager restart
  skill-manager status
  skill-manager web
  skill-manager h | help | --help
  skill-manager version | --version

Configuration:
  ${configPath()}

Environment:
  SKILL_MANAGER_CONFIG  Use a custom config.json path
  SKILL_MANAGER_HOME    Use a custom runtime home
  SKILL_MANAGE_HOME     Runtime home passed to the Python service
  SKILL_MANAGER_PYTHON  Python executable, default: python3`);
}

async function main() {
  const command = process.argv[2] || "h";
  switch (command) {
    case "start":
      await start();
      break;
    case "stop":
      await stop();
      break;
    case "restart":
      await restart();
      break;
    case "status":
      printStatus(loadConfig());
      break;
    case "web":
      web();
      break;
    case "h":
    case "help":
    case "--help":
    case "-h":
      help();
      break;
    case "version":
    case "--version":
    case "-v":
      console.log(PACKAGE_JSON.version);
      break;
    default:
      console.error(`Unknown command: ${command}`);
      help();
      process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
