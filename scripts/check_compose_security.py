#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_ENV = {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_config() -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        fail("docker compose config failed")
    return json.loads(completed.stdout)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def main() -> None:
    os.chdir(Path(__file__).resolve().parents[1])
    config = load_config()
    services = config.get("services", {})
    service = services.get("codex-cli-provider")
    if not service:
        fail("missing codex-cli-provider service")

    ports = service.get("ports") or []
    expected_port = False
    for port in ports:
        if (
            str(port.get("host_ip")) == "127.0.0.1"
            and str(port.get("published")) == "8320"
            and str(port.get("target")) == "8320"
        ):
            expected_port = True
        elif str(port.get("published")):
            fail(f"unexpected published port: {port}")
    if not expected_port:
        fail("missing exact 127.0.0.1:8320:8320 publication")

    if service.get("network_mode") == "host":
        fail("host networking is forbidden")
    if service.get("privileged"):
        fail("privileged mode is forbidden")
    if service.get("pid") == "host" or service.get("ipc") == "host" or service.get("userns_mode") == "host":
        fail("host namespace sharing is forbidden")
    user = service.get("user")
    if user not in (None, "", "0", "0:0", "root"):
        fail("service must intentionally run as root or omit user")
    if service.get("read_only") is not True:
        fail("root filesystem must be read-only")

    cap_drop = {str(item).upper() for item in as_list(service.get("cap_drop"))}
    if "ALL" not in cap_drop:
        fail("cap_drop must include ALL")
    cap_add = {str(item).upper() for item in as_list(service.get("cap_add"))}
    expected_cap_add = {"DAC_OVERRIDE", "FOWNER"}
    if cap_add != expected_cap_add:
        fail(
            "cap_add must contain exactly DAC_OVERRIDE and FOWNER so root can "
            f"access dedicated bind mounts without broader capabilities: {sorted(cap_add)}"
        )

    security_opt = {str(item) for item in as_list(service.get("security_opt"))}
    if "no-new-privileges:true" not in security_opt:
        fail("no-new-privileges must be enabled")
    forbidden_opts = {"seccomp:unconfined", "apparmor:unconfined"}
    if forbidden_opts.intersection(security_opt):
        fail("unconfined security profiles are forbidden")

    volumes = service.get("volumes") or []
    codex_home_mount_ok = False
    codex_work_mount_ok = False
    secret_mount_ok = False
    forbidden_fragments = ("/var/run/docker.sock", ".cli-proxy-api", "/runner")
    for volume in volumes:
        source = str(volume.get("source", ""))
        target = str(volume.get("target", ""))
        if target == "/root/.codex" and source.endswith("/data/codex-home") and not volume.get("read_only"):
            codex_home_mount_ok = True
        elif target == "/workspace" and source.endswith("/data/codex-work") and not volume.get("read_only"):
            codex_work_mount_ok = True
        elif target == "/run/secrets/proxy_api_key" and source.endswith("/data/secrets/proxy_api_key") and volume.get("read_only"):
            secret_mount_ok = True
        if any(fragment in source or fragment in target for fragment in forbidden_fragments):
            fail(f"forbidden mount detected: {source}:{target}")
        if target in {"/home", "/root"} or source in {"/home", "/root"}:
            fail(f"forbidden home/root mount detected: {source}:{target}")
    if not codex_home_mount_ok:
        fail("expected project data/codex-home mount at /root/.codex")
    if not codex_work_mount_ok:
        fail("expected project data/codex-work mount at /workspace")
    if not secret_mount_ok:
        fail("expected read-only project proxy secret file mount")
    if any(str(v.get("target")) not in {"/root/.codex", "/workspace", "/run/secrets/proxy_api_key"} for v in volumes):
        fail("unexpected mount target present")

    env = service.get("environment") or {}
    env_names = set(env if isinstance(env, dict) else [])
    if FORBIDDEN_ENV.intersection(env_names):
        fail("API-key environment variables must not be set in compose")

    tmpfs = {str(item).split(":", 1)[0] for item in as_list(service.get("tmpfs"))}
    if "/tmp" not in tmpfs:
        fail("tmpfs mount for /tmp is required")

    print("compose security checks passed")


if __name__ == "__main__":
    main()
