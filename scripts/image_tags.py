#!/usr/bin/env python3
import argparse
import os
import re
import sys
from pathlib import Path


PROJECT_NAME = "codex-cli-provider"
MAX_DOCKER_TAG_LENGTH = 128
DOCKER_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
RELEASE_TAG_RE = re.compile(rf"^{PROJECT_NAME}-[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9_.-]+)?$")
CANDIDATE_TAG_RE = re.compile(rf"^{PROJECT_NAME}-dev-[A-Za-z0-9][A-Za-z0-9_.-]*$")
SHA_RE = re.compile(r"^[A-Fa-f0-9]{7,64}$")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sanitize_ref_name(ref_name: str) -> str:
    safe = re.sub(r"[^a-z0-9_.-]+", "-", ref_name.strip().lower())
    safe = re.sub(r"[-.]{2,}", "-", safe)
    safe = safe.strip("-._")
    return safe or "ref"


def build_candidate_tag(ref_name: str, sha: str) -> str:
    normalized_sha = sha.strip().lower()
    if not SHA_RE.fullmatch(normalized_sha):
        fail("candidate image tags require a git SHA")

    short_sha = normalized_sha[:12]
    prefix = f"{PROJECT_NAME}-dev-"
    suffix_separator = "-"
    max_ref_length = MAX_DOCKER_TAG_LENGTH - len(prefix) - len(suffix_separator) - len(short_sha)
    ref_part = sanitize_ref_name(ref_name)
    if len(ref_part) > max_ref_length:
        ref_part = ref_part[:max_ref_length].rstrip("-._") or "ref"

    return f"{prefix}{ref_part}{suffix_separator}{short_sha}"


def validate_image_tag(tag: str, kind: str) -> str:
    normalized = tag.strip()
    if not normalized:
        fail("image tag must not be empty")
    if normalized == "latest":
        fail("image tag must not be latest")
    if not DOCKER_TAG_RE.fullmatch(normalized):
        fail(
            "image tag must be a Docker tag of at most 128 characters using "
            "only letters, digits, underscore, period, and dash"
        )

    if kind == "release" and not RELEASE_TAG_RE.fullmatch(normalized):
        fail(f"release image tags must look like {PROJECT_NAME}-0.1.2")
    if kind == "candidate" and not CANDIDATE_TAG_RE.fullmatch(normalized):
        fail(f"candidate image tags must look like {PROJECT_NAME}-dev-branch-abcdef123456")
    if kind == "any" and not (RELEASE_TAG_RE.fullmatch(normalized) or CANDIDATE_TAG_RE.fullmatch(normalized)):
        fail("image tag must be a release or candidate tag")

    return normalized


def write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        fail("GITHUB_OUTPUT is not set")
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def candidate(args: argparse.Namespace) -> None:
    if args.requested.strip():
        tag = validate_image_tag(args.requested, "candidate")
    else:
        tag = build_candidate_tag(args.ref_name, args.sha)
        validate_image_tag(tag, "candidate")

    if args.github_output:
        write_github_output("tag", tag)
    print(tag)


def validate(args: argparse.Namespace) -> None:
    tag = validate_image_tag(args.tag, args.kind)
    print(tag)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve and validate codex-cli-provider image tags.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidate_parser = subparsers.add_parser("candidate", help="Resolve a pre-release candidate image tag.")
    candidate_parser.add_argument("--ref-name", required=True)
    candidate_parser.add_argument("--sha", required=True)
    candidate_parser.add_argument("--requested", default="")
    candidate_parser.add_argument("--github-output", action="store_true")
    candidate_parser.set_defaults(func=candidate)

    validate_parser = subparsers.add_parser("validate", help="Validate an image tag.")
    validate_parser.add_argument("--kind", choices=("release", "candidate", "any"), default="any")
    validate_parser.add_argument("tag")
    validate_parser.set_defaults(func=validate)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
