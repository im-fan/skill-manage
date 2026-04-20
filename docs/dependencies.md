# Dependency Notes

## Python Runtime

- Python 3.10+
- `pip` is required only when `./scripts/start.sh` needs to install entries from `requirements.txt`

## Third-Party Python Packages

The current runtime does not require any third-party Python package.

`requirements.txt` is intentionally kept as the install entry so the startup script can continue using one stable dependency workflow if packages are added later.

## Standard Library Usage

The backend currently relies on Python standard-library modules such as:

- `argparse`
- `http.server`
- `json`
- `logging`
- `os`
- `pathlib`
- `shutil`
- `sqlite3`
- `urllib.parse`
- `webbrowser`

## Operational Notes

- The default server mode is local-only and is intended for loopback hosts such as `127.0.0.1`, `localhost`, and `::1`.
- Remote bind requires explicit opt-in with `SKILL_MANAGE_ALLOW_REMOTE=1`.
