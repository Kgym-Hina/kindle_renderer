#!/usr/bin/env python3
import json
import shlex
import subprocess
import sys
from pathlib import Path


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_ssh_base_args(config):
    host = config.get("host")
    user = config.get("user")
    if not host or not user:
        raise ValueError("connection.json must define both 'host' and 'user'")

    target = f"{user}@{host}"
    args = ["-p", str(config.get("port", 22))]
    key_path = config.get("key_path")
    if key_path:
        args.extend(["-i", str(Path(key_path).expanduser())])
    return target, args


def build_scp_base_args(config):
    args = ["-P", str(config.get("port", 22))]
    key_path = config.get("key_path")
    if key_path:
        args.extend(["-i", str(Path(key_path).expanduser())])
    return args


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(message)
    return result.stdout


def list_local_files(local_glob):
    files = sorted(Path(".").glob(local_glob))
    png_files = [path for path in files if path.is_file()]
    if not png_files:
        raise FileNotFoundError(f"No local files matched {local_glob!r}")
    return png_files


def list_remote_files(target, ssh_args, remote_dir):
    remote_cmd = (
        f"mkdir -p {shlex.quote(remote_dir)} && "
        f"find {shlex.quote(remote_dir)} -maxdepth 1 -type f -name 'db_*.png' -print"
    )
    output = run_command(["ssh", *ssh_args, target, remote_cmd])
    names = set()
    for line in output.splitlines():
        line = line.strip()
        if line:
            names.add(Path(line).name)
    return names


def delete_remote_files(target, ssh_args, remote_dir, filenames):
    if not filenames:
        return
    quoted_files = " ".join(shlex.quote(f"{remote_dir}/{name}") for name in sorted(filenames))
    remote_cmd = f"rm -f {quoted_files}"
    run_command(["ssh", *ssh_args, target, remote_cmd])


def upload_files(target, scp_args, remote_dir, files):
    cmd = ["scp", *scp_args]
    cmd.extend(str(path) for path in files)
    cmd.append(f"{target}:{remote_dir}/")
    run_command(cmd)


def run_refresh_command(target, ssh_args, refresh_command):
    run_command(["ssh", *ssh_args, target, refresh_command])


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("connection.json")
    config = load_json(config_path)

    remote_dir = config.get("remote_dir")
    refresh_command = config.get("refresh_command")
    if not remote_dir:
        raise ValueError("connection.json must define 'remote_dir'")
    if not refresh_command:
        raise ValueError("connection.json must define 'refresh_command'")

    local_glob = config.get("local_glob", "db_*.png")
    local_files = list_local_files(local_glob)
    local_names = {path.name for path in local_files}

    target, ssh_args = build_ssh_base_args(config)
    scp_args = build_scp_base_args(config)
    remote_names = list_remote_files(target, ssh_args, remote_dir)
    stale_remote_names = remote_names - local_names

    delete_remote_files(target, ssh_args, remote_dir, stale_remote_names)
    upload_files(target, scp_args, remote_dir, local_files)
    run_refresh_command(target, ssh_args, refresh_command)

    print(f"Uploaded {len(local_files)} file(s) to {target}:{remote_dir}")
    if stale_remote_names:
        print("Deleted remote stale files:")
        for name in sorted(stale_remote_names):
            print(name)
    else:
        print("Deleted remote stale files: none")
    print("Refresh command executed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
