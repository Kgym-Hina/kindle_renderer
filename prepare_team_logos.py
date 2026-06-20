#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = "https://api.csapi.de"
TEAM_DIR = Path("matches/cs/teams")

TEAM_ALIASES = {
    "Spirit": ["spirit", "team-spirit"],
    "Falcons": ["falcons"],
    "Vitality": ["vitality", "team-vitality"],
    "Natus Vincere": ["natus-vincere", "navi"],
    "MOUZ": ["mouz"],
    "FURIA": ["furia"],
    "Aurora": ["aurora"],
    "Legacy": ["legacy"],
    "G2": ["g2", "g2-esports"],
    "FUT": ["fut", "fut-esports"],
    "BetBoom": ["betboom", "betboom-team"],
    "9z": ["9z", "9z-team"],
    "The MongolZ": ["the-mongolz", "mongolz"],
    "GamerLegion": ["gamerlegion"],
    "Astralis": ["astralis"],
    "B8": ["b8", "b8-esports"],
    "PARIVISION": ["parivision"],
    "Monte": ["monte"],
    "MIBR": ["mibr"],
    "magic": ["magic"],
}


def slugify_team_name(value):
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)


def api_get(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def image_get(url, referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/png,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as response:
        return response.read()


def candidate_urls(team_name):
    slug = slugify_team_name(team_name)
    aliases = TEAM_ALIASES.get(team_name, [])
    seen = set()

    exeskins_urls = []
    for alias in [slug, *aliases]:
        if alias and alias not in seen:
            seen.add(alias)
            exeskins_urls.append(
                f"https://exeskins.com/_next/image?url=%2Fapi%2Fteam-logos%2Ffile%2F{alias}.png&w=128&q=75"
            )

    raw_urls = []
    for alias in [slug, *aliases]:
        if alias:
            raw_urls.append(f"https://raw.githubusercontent.com/lootmarket/esport-team-logos/master/cs/{alias}/{alias}-logo.png")
            raw_urls.append(f"https://raw.githubusercontent.com/lootmarket/esport-team-logos/master/csgo/{alias}/{alias}-logo.png")
    return exeskins_urls + raw_urls


def download_team_logo(team_name):
    TEAM_DIR.mkdir(parents=True, exist_ok=True)
    target = TEAM_DIR / f"{slugify_team_name(team_name)}.png"
    for url in candidate_urls(team_name):
        try:
            payload = image_get(url, referer="https://exeskins.com/")
            if payload:
                target.write_bytes(payload)
                return target, url
        except (HTTPError, URLError, TimeoutError, OSError):
            continue
    return None, None


def main():
    rankings = api_get(f"{API_BASE}/rankings/")
    top20 = [entry["name"] for entry in rankings["rankings"][:20]]
    missing = []
    for team_name in top20:
        target = TEAM_DIR / f"{slugify_team_name(team_name)}.png"
        if target.exists():
            print(f"exists {target}")
            continue
        path, source = download_team_logo(team_name)
        if path:
            print(f"saved {path} <- {source}")
        else:
            print(f"missing {team_name}")
            missing.append(team_name)
    if missing:
        print("\nStill missing logos for:")
        for team_name in missing:
            print(team_name)
        sys.exit(1)


if __name__ == "__main__":
    main()
