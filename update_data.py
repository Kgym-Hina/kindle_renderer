#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://api.csapi.de"
TEAM_LOGO_DIR = "matches/cs/teams"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api_get(path, params=None):
    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def now_text(offset_hours):
    tz = timezone(timedelta(hours=offset_hours))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def slugify_team_name(value):
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)


def normalize_name(value):
    return str(value or "").strip().lower()


def score_text(match):
    team1 = match.get("team1", {})
    team2 = match.get("team2", {})
    score1 = team1.get("score")
    score2 = team2.get("score")
    if score1 is not None and score2 is not None:
        return f"{score1} : {score2}"
    return match.get("time", "TBD")


def subtitle_text(match):
    parts = []
    if match.get("date"):
        parts.append(str(match["date"]))
    if match.get("event"):
        parts.append(str(match["event"]))
    return " · ".join(parts)


def match_type_text(match):
    best_of = match.get("best_of")
    if best_of:
        return f"BO{best_of}"
    return match.get("match_type", "")


def meta_text(match):
    maps = match.get("maps") or []
    if maps:
        names = [m.get("name") for m in maps if m.get("name")]
        return " / ".join(names[:3])
    return match.get("meta", "")


def build_match_module(match, fallback_title, team_logos):
    team1 = match.get("team1", {})
    team2 = match.get("team2", {})
    home = match.get("home", team1.get("name", "TBD"))
    away = match.get("away", team2.get("name", "TBD"))
    return {
        "type": "match",
        "show": match.get("show", True),
        "title": match.get("title", fallback_title),
        "home": home,
        "away": away,
        "home_logo": match.get("home_logo", team_logos.get(home, f"{TEAM_LOGO_DIR}/{slugify_team_name(home)}.png")),
        "away_logo": match.get("away_logo", team_logos.get(away, f"{TEAM_LOGO_DIR}/{slugify_team_name(away)}.png")),
        "score": match.get("score", score_text(match)),
        "subtitle": match.get("subtitle", subtitle_text(match)),
        "match_type": match.get("match_type", match_type_text(match)),
        "meta": match.get("meta", meta_text(match)),
        "use_mono": match.get("use_mono", True),
    }


def find_team_id(team_name):
    items = api_get("/teams/", {"name": team_name, "limit": 5, "offset": 0})
    wanted = normalize_name(team_name)
    for item in items:
        if normalize_name(item.get("name")) == wanted:
            return item.get("id")
    return items[0].get("id") if items else None


def fetch_last_match_for_team(team_name, fallback_title, team_logos):
    team_id = find_team_id(team_name)
    if not team_id:
        return None
    matches = api_get(f"/teams/{team_id}/matchhistory", {"limit": 5, "offset": 0})
    if not matches:
        return None
    return build_match_module(matches[0], fallback_title, team_logos)


def collect_last_match(config):
    fallback_title = config.get("fallback_match_title", "Major Match")
    team_logos = config.get("team_logos", {})
    teams = config.get("teams", [])
    for team_name in teams:
        try:
            match = fetch_last_match_for_team(team_name, fallback_title, team_logos)
            if match:
                return match
        except Exception as exc:
            print(f"Warning: failed to fetch last match for {team_name}: {exc}", file=sys.stderr)
    return None


def ssh_run(server, remote_script):
    host = server["host"]
    user = server.get("user", "root")
    port = str(server.get("port", 22))
    key_path = Path(server["key_path"]).expanduser()
    cmd = [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
        remote_script,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ssh failed")
    return result.stdout.strip()


def parse_server_metrics(raw):
    metrics = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        metrics[key.strip()] = value.strip()
    return metrics


def format_cpu(value):
    text = str(value or "").strip()
    if not text or text == "N/A":
        return "N/A"
    if text.endswith("%"):
        return text
    try:
        return f"{float(text):.1f}%"
    except ValueError:
        return text


def format_uptime(value):
    text = " ".join(str(value or "").strip().split())
    if not text or text == "N/A":
        return "N/A"

    text = re.sub(r",?\s*load averages?:.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r",?\s*\d+\s+users?$", "", text, flags=re.IGNORECASE)
    text = text.strip(" ,")

    text = text.replace("days", "d").replace("day", "d")
    text = text.replace("hours", "h").replace("hour", "h")
    text = text.replace("hrs", "h").replace("hr", "h")
    text = text.replace("minutes", "m").replace("minute", "m")
    text = text.replace("mins", "m").replace("min", "m")

    text = re.sub(r"(\d+):(\d+)", r"\1h \2m", text)
    text = text.replace(",", " ")
    text = re.sub(r"(\d+)\s+d\b", r"\1d", text)
    text = re.sub(r"(\d+)\s+h\b", r"\1h", text)
    text = re.sub(r"(\d+)\s+m\b", r"\1m", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect_server_status(server):
    remote_script = (
        "CPU=$(top -l 1 | awk '/CPU usage/ {gsub(\"%\",\"\",$3); print $3}') 2>/dev/null; "
        "if [ -z \"$CPU\" ]; then CPU=$(LC_ALL=C top -bn1 | awk '/Cpu\\(s\\)|%Cpu/ {for(i=1;i<=NF;i++) if ($i ~ /id,/) {idle=$(i-1); gsub(\",\",\"\",idle); print 100-idle; exit}}'); fi; "
        "RAM=$(free -m 2>/dev/null | awk '/Mem:/ {printf \"%d%%\", ($3/$2)*100}'); "
        "if [ -z \"$RAM\" ]; then RAM=$(vm_stat | awk 'BEGIN{pagesize=4096} /Pages active/ {active=$3} /Pages wired down/ {wired=$4} /Pages occupied by compressor/ {comp=$5} /Pages free/ {free=$3} /Pages speculative/ {spec=$3} END {gsub(\"\\\\.\",\"\",active); gsub(\"\\\\.\",\"\",wired); gsub(\"\\\\.\",\"\",comp); gsub(\"\\\\.\",\"\",free); gsub(\"\\\\.\",\"\",spec); used=active+wired+comp; total=used+free+spec; if (total>0) printf \"%d%%\", (used/total)*100;}'); fi; "
        "UP=$(uptime | sed 's/^.*up *//; s/, *[0-9]* users.*$//; s/, *load average:.*$//'); "
        "echo CPU=${CPU:-N/A}; echo RAM=${RAM:-N/A}; echo Uptime=${UP:-N/A}"
    )
    raw = ssh_run(server, remote_script)
    metrics = parse_server_metrics(raw)
    return {
        "type": "status",
        "show": True,
        "title": server.get("title") or server.get("name") or server["host"],
        "items": [
            {"label": "CPU", "value": format_cpu(metrics.get("CPU", "N/A"))},
            {"label": "RAM", "value": metrics.get("RAM", "N/A")},
            {"label": "Uptime", "value": format_uptime(metrics.get("Uptime", "N/A"))},
        ],
    }


def collect_status_modules(config):
    modules = []
    for server in config.get("servers", []):
        try:
            modules.append(collect_server_status(server))
        except Exception as exc:
            modules.append(
                {
                    "type": "status",
                    "show": True,
                    "title": server.get("title") or server.get("name") or server.get("host", "Server"),
                    "items": [
                        {"label": "CPU", "value": "N/A"},
                        {"label": "RAM", "value": "N/A"},
                        {"label": "Uptime", "value": "SSH Error"},
                    ],
                }
            )
            print(f"Warning: failed to collect server status for {server.get('host')}: {exc}", file=sys.stderr)
    return modules


def collect_matches(config):
    modules = []
    last_match = collect_last_match(config)
    if last_match:
        modules.append(last_match)
    return modules


def build_payload(config):
    offset = int(config.get("timezone_offset_hours", 8))
    modules = []
    modules.extend(collect_matches(config))
    modules.extend(collect_status_modules(config))
    modules.extend(config.get("static_modules", []))
    return {
        "title": config.get("title", "Dashboard"),
        "subtitle": now_text(offset),
        "modules": modules,
    }


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.json")
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data.json")
    config = load_json(config_path)
    payload = build_payload(config)
    write_json(output_path, payload)
    print(output_path.name)


if __name__ == "__main__":
    main()
