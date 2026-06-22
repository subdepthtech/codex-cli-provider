#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8320"
DEFAULT_MODEL = "codex-cli-default"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        fail(f"token file not found: {path}")
    if not token:
        fail(f"token file is empty: {path}")
    return token


def request_json(
    method: str,
    url: str,
    *,
    timeout: int,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        body = error.read()
        status = error.code
    except urllib.error.URLError as error:
        fail(f"request failed for {url}: {error.reason}")

    if not body:
        return status, {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        fail(f"non-JSON response from {url}: HTTP {status}")
    if not isinstance(parsed, dict):
        fail(f"unexpected JSON response from {url}: HTTP {status}")
    return status, parsed


def expect_status(status: int, expected: int, label: str, body: dict[str, Any]) -> None:
    if status != expected:
        fail(f"{label} returned HTTP {status}, expected {expected}: {json.dumps(body, sort_keys=True)[:500]}")


def smoke_test(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")
    token = read_token(args.token_file)
    auth_headers = {"Authorization": f"Bearer {token}"}

    status, body = request_json("GET", f"{base_url}/healthz", timeout=args.timeout)
    expect_status(status, 200, "healthz", body)
    if body.get("status") != "ok":
        fail(f"healthz returned unexpected body: {body}")
    print("healthz ok")

    status, body = request_json("GET", f"{base_url}/v1/models", timeout=args.timeout)
    expect_status(status, 401, "unauthenticated /v1/models", body)
    print("auth gate ok")

    status, body = request_json("GET", f"{base_url}/v1/models", timeout=args.timeout, headers=auth_headers)
    expect_status(status, 200, "authenticated /v1/models", body)
    models = body.get("data")
    if not isinstance(models, list) or not any(isinstance(model, dict) and model.get("id") == args.model for model in models):
        fail(f"{args.model} missing from /v1/models response")
    print("models ok")

    if args.chat:
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": args.prompt}],
        }
        status, body = request_json(
            "POST",
            f"{base_url}/v1/chat/completions",
            timeout=args.chat_timeout,
            headers=auth_headers,
            payload=payload,
        )
        expect_status(status, 200, "chat completion", body)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            fail("chat completion response did not include choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            fail("chat completion response did not include non-empty message content")
        print("chat completion ok")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test a running codex-cli-provider container.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token-file", type=Path, default=Path("data/secrets/proxy_api_key"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--chat-timeout", type=int, default=240)
    parser.add_argument("--chat", action="store_true", help="Also run one live Codex-backed chat completion.")
    parser.add_argument(
        "--prompt",
        default="Reply with one short sentence confirming the image smoke test ran.",
        help="Prompt used only when --chat is set.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    smoke_test(args)


if __name__ == "__main__":
    main()
