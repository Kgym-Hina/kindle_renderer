# Kindle Renderer

[中文说明](README.zh-CN.md)

Generate black-and-white dashboard images for Kindle-style screens.

## Features

- Renders dashboard pages as `db_1.png`, `db_2.png`, ...
- Shows the latest match for a followed CS team via `https://api.csapi.de`
- Reads team logos from local files under `matches/cs/teams/`
- Collects server status over SSH:
  - `CPU`
  - `RAM`
  - `Uptime`

## Files

- `main.py`: renders `data.json` into page images
- `update_data.py`: generates `data.json`
- `prepare_team_logos.py`: downloads local team logos for ranked teams
- `sync_kindle_images.py`: syncs rendered `db_*.png` images to a remote host and runs a refresh command
- `run_full_sync.py`: runs data generation, image rendering, and remote sync in one command
- `kindle/`: Kindle-side Go app, KUAL extension files, and release packaging script
- `config.json`: local private config, ignored by git
- `config.json.template`: config template to copy from
- `connection.json`: remote sync config, ignored by git
- `connection.json.template`: remote sync config template

## Setup

1. Create your local config:

```bash
cp config.json.template config.json
```

2. Edit `config.json`:

- Set `teams` to the CS teams you follow
- Set `servers` with real SSH host/user/key settings
- Adjust title, timezone, and local logo paths as needed

3. Prepare team logos:

```bash
python3 prepare_team_logos.py
```

4. Generate data and render images:

```bash
python3 update_data.py
python3 main.py data.json dashboard.png
```

5. Sync rendered images to the remote device and trigger refresh:

```bash
cp connection.json.template connection.json
python3 sync_kindle_images.py
```

`connection.json` fields:

```json
{
  "host": "203.0.113.10",
  "port": 22,
  "user": "root",
  "key_path": "~/.ssh/id_ed25519",
  "remote_dir": "/path/to/remote/dashboard",
  "refresh_command": "cd /path/to/remote/dashboard && ./refresh.sh",
  "local_glob": "db_*.png"
}
```

Behavior:

- Uploads all local files matching `local_glob` to `remote_dir`
- Overwrites remote files with the same name
- Deletes remote `db_*.png` files that do not exist locally anymore
- Executes `refresh_command` over SSH after upload

6. Run the full pipeline in one command:

```bash
python3 run_full_sync.py
```

Optional arguments:

```bash
python3 run_full_sync.py config.json data.json dashboard.png connection.json
```

## Kindle Extension

The `kindle/` directory contains the Kindle-side app and KUAL packaging files.

Build the release package locally:

```bash
cd kindle
./build_kual_package.sh
```

This produces:

- `kindle/dist/kindle-dashboard.zip`

Extract the zip so the Kindle contains:

```text
/mnt/us/extensions/kindle-dashboard/config.xml
/mnt/us/extensions/kindle-dashboard/menu.json
/mnt/us/extensions/kindle-dashboard/bin/start.sh
/mnt/us/extensions/kindle-dashboard/bin/stop.sh
/mnt/us/extensions/kindle-dashboard/bin/dashboard-kindle
/mnt/us/extensions/kindle-dashboard/config
```

The extension provides KUAL menu entries to start and stop the dashboard app.

## Releases

GitHub Actions automatically builds a KUAL package and creates a GitHub Release when a tag is pushed.

## Team Logos

Logos are loaded only from local files.

Expected path pattern:

```text
matches/cs/teams/<team-slug>.png
```

Examples:

- `matches/cs/teams/falcons.png`
- `matches/cs/teams/vitality.png`
- `matches/cs/teams/spirit.png`

If a logo is missing, the renderer prints a warning and falls back to a placeholder.

## Server Status

Each server entry in `config.json` should include:

```json
{
  "title": "My Server",
  "host": "your-host.example.com",
  "port": 22,
  "user": "root",
  "key_path": "~/.ssh/id_ed25519"
}
```

The generator uses the local `ssh` binary and your specified private key.

If SSH collection fails, the status card still renders with fallback values.
