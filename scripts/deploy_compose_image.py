#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.image_tags import validate_image_tag


REQUIRED_DIRS = (
    Path("data/codex-home"),
    Path("data/codex-work"),
    Path("data/secrets"),
)
REQUIRED_FILES = (
    Path(".env"),
    Path("data/secrets/proxy_api_key"),
)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, env=env, check=True)


def check_local_state() -> None:
    missing_dirs = [str(path) for path in REQUIRED_DIRS if not path.is_dir()]
    missing_files = [str(path) for path in REQUIRED_FILES if not path.is_file()]
    if missing_dirs or missing_files:
        missing = ", ".join(missing_dirs + missing_files)
        fail(f"missing local deployment state: {missing}")


def deploy(args: argparse.Namespace) -> None:
    image_tag = validate_image_tag(args.image_tag, args.tag_kind)
    image_ref = f"{args.image_repository.rstrip(':')}:{image_tag}"

    os.chdir(args.repo_dir.resolve())
    check_local_state()

    env = os.environ.copy()
    env["CODEX_CLI_PROVIDER_IMAGE"] = image_ref
    env["COMPOSE_FILE"] = "docker-compose.image.yml"

    run(["python3", "scripts/check_compose_security.py"], env=env)
    run(["docker", "compose", "-f", "docker-compose.image.yml", "pull"], env=env)
    run(["docker", "compose", "-f", "docker-compose.image.yml", "up", "-d", "--remove-orphans"], env=env)
    run(["python3", "scripts/smoke_test_provider.py", "--base-url", args.base_url], env=env)
    if args.chat_smoke:
        run(["python3", "scripts/smoke_test_provider.py", "--base-url", args.base_url, "--chat"], env=env)

    print(f"deployed {image_ref}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy a published codex-cli-provider image with Compose.")
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--image-repository", required=True, help="Image repository without tag, for example ghcr.io/org/repo.")
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--tag-kind", choices=("candidate", "release", "any"), default="any")
    parser.add_argument("--base-url", default="http://127.0.0.1:8320")
    parser.add_argument("--chat-smoke", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    deploy(args)


if __name__ == "__main__":
    main()
