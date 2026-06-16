# 🗃️ Skill Manager

English | [中文](./README-zh.md)

![Agent Skill Manager](./resource/skill-manage.jpg)

**Open-source, local-first agent skill manager for Codex, ClaudeCode, Hermes, and OpenClaw.**

Agent Skill Manager is a local web console for organizing shared skill folders across multiple AI agents. It focuses on one job: keep your SKILL repository, agent-mounted links, invalid directories, and local skill library manageable from one place.

It is designed for developers who search for an open-source local agent skill manager, a SKILL repository manager, a multi-agent skill library UI, or a lightweight tool for symlink cleanup and invalid skill link cleanup across Codex, ClaudeCode, Hermes, and OpenClaw.

The project stays intentionally small, but it now uses an engineered layout: the Python backend lives in `src/skill_manage/`, the UI lives in `web/`, launch helpers live in `scripts/`, and source-development runtime artifacts are written to `data/` and `logs/`. When installed as the npm CLI, runtime data moves to the configured user runtime home instead of the package install directory.

The default deployment model is local-only: the built-in server is intended to run on loopback addresses such as `127.0.0.1`, `localhost`, or `::1`.

## Search Keywords

- `agent skill manager`
- `open source local-first skill manager`
- `SKILL repository manager`
- `multi-agent skill library`
- `Codex skills manager`
- `ClaudeCode skills manager`
- `Hermes skills manager`
- `OpenClaw skills manager`
- `symlink-based skill mounting`
- `invalid link cleanup`
- `local skill repository cleanup`
- `SKILL.md directory scanner`

## What The App Does

- Scan local skill sources in two modes:
  - `skill_root`: recursively collect directories that contain `SKILL.md`
  - `skill_dir`: register one standalone skill directory directly
- Maintain a local SKILL repository with persisted metadata, health status, and search support.
- Manage agent directories from a single UI, including current path, default path, mounted symlinks, direct folders, and invalid entries.
- Move direct agent skills into the shared repository and keep them mounted through managed symlinks.
- Rescan sources and agent directories, clean invalid links, and compare similar skills by content.
- Persist scan roots, local skills, agent settings, managed links, and operation logs into SQLite.

## Current UI Tabs

### SKILL Repository

- Add scan roots and rescan them in place.
- Edit an existing scan source from the card dialog and rescan immediately after saving.
- Browse repository entries as cards and remove records when needed.
- Run similarity scanning against healthy repository skills.

### Agent List

- Focus on one current agent at a time and switch agents from the inline selector.
- Review current configured path, default path, mounted skills, direct skill folders, and invalid links.
- Search addable skills from the shared repository and mount them into the current agent.
- Import direct folders into the repository, move them to another repository root, or delete them intentionally.
- Run similarity scanning inside the current agent context.

### Agent Manage

- Create a custom agent record manually.
- Auto-discover built-in agent directories for `Codex`, `ClaudeCode`, `OpenClaw`, and `Hermes`.
- Keep only the current configured path and default path in the list view.
- Edit an agent, set it as current, toggle visible/hidden state, and delete it from the registry.

### System

- Show system status cards for service state, service URL, SQLite path, and Python version.
- Show recent operation logs for write/update style actions without startup noise.

## Language Switch

- The top-right `中 / En` control switches fixed UI copy between Chinese and English.
- Chinese is the default language.
- The selected language is stored in browser `localStorage` with the key `skill-manage-language`.

## Supported Agents

The current implementation supports these built-in targets:

| Agent | Default path |
| --- | --- |
| Codex | `~/.codex/skills` |
| ClaudeCode | `~/.claude/skills` |
| Hermes | `~/.hermes/skills` |
| OpenClaw | `~/.openclaw/skills` |

Auto-discovery scans exactly one built-in default path per agent. After registration, the UI keeps both the current configured path and the default path for each agent.

## Project Layout

| Path | Purpose |
| --- | --- |
| `src/skill-manage-server.py` | Thin compatibility entry that boots the packaged backend |
| `src/skill_manage/` | Python backend package for startup, HTTP handlers, services, repositories, database, and utilities |
| `bin/skill-manager.js` | npm CLI for start/stop/restart/status/web/help/version |
| `web/skill-manage.html` | Single-file UI for the full local management console |
| `scripts/start.sh` | Startup helper that checks Python, installs dependencies, frees the configured port, and launches the service |
| `data/skill-manage.sqlite3` | Source-development SQLite database |
| `logs/skill-manage.log` | Source-development log file |
| `requirements.txt` | Python dependency list used by the startup script |
| `docs/dependencies.md` | Dependency inventory and runtime notes |
| `docs/npm-install-publish-use-zh.md` | Source install, npm packaging, publishing, local/global install, and CLI usage tutorial |

## Quick Start

### Requirements

- Python 3.10+
- A Unix-like environment is recommended
- Filesystem symlink support

Notes:

- Startup checks whether the Python environment is healthy before launch.
- If Python is not available or broken, startup fails fast with a message asking you to check Python.
- If Python is healthy, `./scripts/start.sh` installs dependencies from `requirements.txt` automatically before starting the service.
- The backend is standard-library-first, but the project still keeps `requirements.txt` as the install entry for startup automation.
- The default host is `127.0.0.1`.

### Install With npm

The npm package name is scoped, but the global command is `skill-manager`:

```bash
npm install -g @im-fan/skill-manage
```

Use the CLI to manage the local Python service:

```bash
skill-manager start
skill-manager status
skill-manager web
skill-manager restart
skill-manager stop
skill-manager h
skill-manager version
```

The first `start`, `status`, or `web` command creates the default config file:

```text
~/.skill-manager/config.json
```

Default config:

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "runtimeHome": "~/.skill-manager"
}
```

The CLI stores runtime files under `runtimeHome`:

```text
~/.skill-manager/
  config.json
  data/skill-manage.sqlite3
  logs/skill-manage.log
  run/skill-manager.pid
  run/skill-manager.json
```

To change the port, edit `server.port` in the config file and run `skill-manager restart`. `skill-manager start` is restart-friendly: if the service is already running, it stops the old managed process first; if the configured port is occupied, it kills the owning process and then starts the service.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `SKILL_MANAGER_CONFIG` | Use a custom config file path |
| `SKILL_MANAGER_HOME` | Override the default CLI home, including the default config path |
| `SKILL_MANAGE_HOME` | Override the Python runtime home for database and logs |
| `SKILL_MANAGER_PYTHON` | Select the Python executable used by the CLI |

`SKILL_MANAGER_HOME` is preferred for CLI configuration. The CLI passes the resolved `runtimeHome` to Python as `SKILL_MANAGE_HOME`, so SQLite and logs are not written into the npm package directory.

For the full source install, npm pack, publishing, local/global npm install, and `skill-manager` usage flow, see [Skill Manager 源码安装、npm 打包发布与使用教程](./docs/npm-install-publish-use-zh.md).

### Start The Service

For npm/global installs, start the service with:

```bash
skill-manager start
skill-manager web
```

For source development, run the compatibility entry:

```bash
python3 src/skill-manage-server.py --open
```

Run the packaged module:

```bash
PYTHONPATH=src python3 -m skill_manage --open
```

Run the helper script:

```bash
./scripts/start.sh
```

Default address:

```text
http://127.0.0.1:8765/
```

After startup succeeds, the Python service logs a startup success message and the bound port.

## Typical Workflow

1. Add one or more scan roots in the `SKILL Repository` tab.
2. Let the scanner collect directories that contain `SKILL.md`.
3. Open `Agent Manage` and auto-discover or manually register the agent directories you actually use.
4. Switch to `Agent List`, pick the current agent, and mount reusable skills from the shared repository.
5. Normalize direct folders by importing them into the shared repository or moving them between repository roots.
6. Use the similarity scanners to find duplicated or overlapping skills before the library drifts again.

## Common Use Cases

- Build one shared local SKILL repository for multiple AI coding agents.
- Clean old symlinks, invalid skill mounts, and duplicated skill folders.
- Migrate direct skill folders from agent directories into a managed repository.
- Review which skills are mounted into the current agent and rescan them quickly.
- Keep a local-first workflow instead of relying on a remote marketplace or sync service.

## HTTP API

The UI talks to a small local JSON API. Current endpoints include:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/state` | Fetch the full page state |
| `GET` | `/api/agents` | Fetch registered agents |
| `GET` | `/api/operation-logs` | Fetch paginated operation logs |
| `POST` | `/api/scan-roots` | Save and scan one scan root |
| `POST` | `/api/scan-roots/update` | Update one scan root and rescan it |
| `POST` | `/api/scan-roots/rescan` | Rescan all scan roots |
| `POST` | `/api/scan-roots/item/rescan` | Rescan one saved scan root |
| `POST` | `/api/local-skills` | Add one local skill manually |
| `POST` | `/api/local-skills/find-similar` | Find similar skills in the repository |
| `POST` | `/api/local-skills/move` | Move a local skill to another repository root |
| `POST` | `/api/agents` | Create one agent |
| `POST` | `/api/agents/update` | Update one agent |
| `POST` | `/api/agents/auto-discover` | Auto-discover built-in agent directories |
| `POST` | `/api/agents/visibility` | Toggle agent visible/hidden state |
| `POST` | `/api/agents/{agent}/path` | Save the configured path for one agent |
| `POST` | `/api/agents/{agent}/scan` | Rescan one agent directory |
| `POST` | `/api/agents/{agent}/scan-default-to-local` | Scan the current configured directory into the repository |
| `POST` | `/api/agents/{agent}/link` | Mount one repository skill into an agent directory |
| `POST` | `/api/agents/{agent}/move-direct-to-local` | Move one direct agent skill into the repository |
| `POST` | `/api/agents/{agent}/delete-direct-skill` | Delete one direct skill folder from an agent directory |
| `POST` | `/api/agents/{agent}/cleanup-invalid` | Remove invalid symlinks from an agent directory |
| `POST` | `/api/agents/{agent}/find-similar` | Find similar skills inside one agent context |
| `DELETE` | `/api/scan-roots?path=...` | Remove one saved scan root |
| `DELETE` | `/api/links?path=...` | Remove one mounted symlink |
| `DELETE` | `/api/local-skills?path=...` | Delete one local skill record |
| `DELETE` | `/api/agents?agent_code=...` | Delete one registered agent |

## Runtime And Safety Notes

- State is stored in `data/skill-manage.sqlite3` during source development, or in `<runtimeHome>/data/skill-manage.sqlite3` when launched by the npm CLI.
- Runtime logs are written to `logs/skill-manage.log` during source development, or in `<runtimeHome>/logs/skill-manage.log` when launched by the npm CLI.
- The app uses SQLite `DELETE` journal mode, so `sqlite3-wal` and `sqlite3-shm` should not be kept around during normal operation.
- Operation logs are intended for meaningful write/update actions, not noisy initialization messages.
- Invalid-link cleanup removes symlink entries only; it does not delete real skill directories.
- Deleting a direct skill folder from an agent directory is destructive and should be used intentionally.
- The built-in server is local-only by default and rejects non-loopback bind hosts unless `SKILL_MANAGE_ALLOW_REMOTE=1` is set explicitly.
- CORS is restricted to loopback web origins instead of wildcard access.

## License

This project is released under the MIT License. See [LICENSE](./LICENSE).

## Scope

This project is for local skill management. It does not try to be a remote sync service or a marketplace.

It is a good fit for:

- personal multi-agent setups
- shared local skill repositories
- cleanup of long-lived skill directories
- teams that want one lightweight local control panel instead of multiple ad hoc folders

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=im-fan/skill-manage&type=date&legend=top-left)](https://www.star-history.com/?repos=im-fan%2Fskill-manage&type=date&legend=top-left)
