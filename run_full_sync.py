#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.json")
    data_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data.json")
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("dashboard.png")
    connection_path = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("connection.json")

    steps = [
        ("[1/3] Generate data", [sys.executable, "update_data.py", str(config_path), str(data_path)]),
        ("[2/3] Render images", [sys.executable, "main.py", str(data_path), str(output_path)]),
        ("[3/3] Upload images", [sys.executable, "sync_kindle_images.py", str(connection_path)]),
    ]

    for title, cmd in steps:
        print(title)
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    print("All steps completed successfully")


if __name__ == "__main__":
    main()
