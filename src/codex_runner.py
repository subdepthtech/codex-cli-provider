import asyncio
import json
import logging
import os
import shutil
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("codex_cli_provider.runner")

PINNED_CODEX_VERSION = "codex-cli 0.141.0"
DEFAULT_CODEX_HOME = "/root/.codex"
DEFAULT_WORK_DIR = "/workspace"
STDERR_LIMIT = 64_000
STDOUT_LIMIT = 256_000
FORBIDDEN_ENV_VARS = ("OPENAI_API_KEY",)
FORBIDDEN_EVENT_FRAGMENTS = (
    "exec_command",
    "shell",
    "command",
    "file_edit",
    "apply_patch",
    "mcp",
    "web_search",
    "browser",
    "subagent",
    "multi_agent",
    "tool_call",
)


class RunnerError(Exception):
    def __init__(self, kind: str, message: str = "upstream error") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class RunnerSettings:
    codex_home: Path
    work_dir: Path
    codex_bin: str
    default_model: str | None
    request_timeout_seconds: int

    @classmethod
    def from_env(cls, default_model: str | None, request_timeout_seconds: int) -> "RunnerSettings":
        return cls(
            codex_home=Path(os.environ.get("CODEX_HOME", DEFAULT_CODEX_HOME)).resolve(),
            work_dir=Path(os.environ.get("CODEX_WORK_DIR", DEFAULT_WORK_DIR)).resolve(),
            codex_bin=os.environ.get("CODEX_BIN", "codex"),
            default_model=default_model,
            request_timeout_seconds=request_timeout_seconds,
        )


def fail_if_api_key_environment() -> None:
    present = [name for name in FORBIDDEN_ENV_VARS if os.environ.get(name)]
    if present:
        raise RuntimeError("OPENAI_API_KEY is not allowed")


def build_child_env(codex_home: str, child_home: str) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": child_home,
        "CODEX_HOME": codex_home,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
    }
    for name in ("SSL_CERT_FILE", "CODEX_CA_CERTIFICATE"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def build_codex_command(
    codex_bin: str,
    work_dir: str,
    output_file: str,
    model: str | None = None,
) -> list[str]:
    command = [
        codex_bin,
        "--ask-for-approval",
        "never",
        "exec",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--cd",
        work_dir,
        "--sandbox",
        "danger-full-access",
        "--output-last-message",
        output_file,
    ]
    if model:
        command.extend(["--model", model])
    command.append("-")
    return command


def write_codex_config(settings: RunnerSettings) -> None:
    settings.codex_home.mkdir(parents=True, exist_ok=True)
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    config_path = settings.codex_home / "config.toml"
    child_home = str((settings.work_dir / ".empty-home").resolve()).replace("\\", "\\\\").replace('"', '\\"')
    path_value = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin").replace("\\", "\\\\").replace('"', '\\"')
    model_line = f'model = "{settings.default_model}"\n' if settings.default_model else ""
    config = f"""# Generated for codex-cli-provider.
{model_line}approval_policy = "never"
sandbox_mode = "danger-full-access"
cli_auth_credentials_store = "file"
forced_login_method = "chatgpt"
allow_login_shell = false
web_search = "disabled"
check_for_update_on_startup = false

[history]
persistence = "none"

[analytics]
enabled = false

[feedback]
enabled = false

[otel]
exporter = "none"
trace_exporter = "none"
metrics_exporter = "none"
log_user_prompt = false

[shell_environment_policy]
inherit = "none"
include_only = ["PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL"]
ignore_default_excludes = false
experimental_use_profile = false

[shell_environment_policy.set]
PATH = "{path_value}"
HOME = "{child_home}"
LANG = "C.UTF-8"
LC_ALL = "C.UTF-8"

[features]
shell_tool = false
unified_exec = false
shell_snapshot = false
apps = false
browser_use = false
browser_use_external = false
computer_use = false
hooks = false
plugins = false
multi_agent = false
skill_mcp_dependency_install = false
memories = false
enable_mcp_apps = false
standalone_web_search = false

[agents]
max_threads = 1
max_depth = 1

[mcp_servers]
"""
    config_path.write_text(config, encoding="utf-8")
    config_path.chmod(0o600)


def ensure_work_repo(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / ".empty-home").mkdir(parents=True, exist_ok=True)
    if not (work_dir / ".git").exists():
        result = shutil.which("git")
        if not result:
            raise RuntimeError("git unavailable")
        import subprocess

        completed = subprocess.run(
            [result, "init", "-q", str(work_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("work repo initialization failed")


async def run_command_capture(command: list[str], env: dict[str, str], cwd: Path, timeout: int = 20) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(cwd),
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        terminate_process_group(proc)
        await reap_process(proc)
        raise
    return proc.returncode or 0, stdout[:STDOUT_LIMIT], stderr[:STDERR_LIMIT]


async def verify_codex_version(settings: RunnerSettings) -> None:
    env = build_child_env(str(settings.codex_home), str(settings.work_dir / ".empty-home"))
    code, stdout, _ = await run_command_capture([settings.codex_bin, "--version"], env, settings.work_dir, timeout=10)
    version = stdout.decode("utf-8", errors="replace").strip()
    if code != 0 or version != PINNED_CODEX_VERSION:
        raise RuntimeError("codex version mismatch")


async def verify_login(settings: RunnerSettings) -> None:
    env = build_child_env(str(settings.codex_home), str(settings.work_dir / ".empty-home"))
    code, _, _ = await run_command_capture([settings.codex_bin, "login", "status"], env, settings.work_dir, timeout=15)
    if code != 0:
        raise RuntimeError("codex login unavailable")


async def initialize_environment(settings: RunnerSettings) -> None:
    fail_if_api_key_environment()
    ensure_work_repo(settings.work_dir)
    write_codex_config(settings)
    await verify_codex_version(settings)
    await verify_login(settings)


def classify_exception(exc: Exception) -> str:
    text = str(exc).lower()
    if "version" in text:
        return "version"
    if "login" in text or "auth" in text:
        return "auth"
    if "sandbox" in text:
        return "safety"
    if "timeout" in text:
        return "timeout"
    return "startup"


def classify_failure(returncode: int, stderr: bytes) -> str:
    text = stderr.decode("utf-8", errors="replace").lower()
    if "not logged in" in text or "authentication" in text or "login" in text:
        return "auth"
    if "rate limit" in text or "too many requests" in text or "429" in text:
        return "rate_limit"
    if returncode != 0:
        return "upstream"
    return "upstream"


def event_stream_has_forbidden_tools(stdout: bytes) -> bool:
    for raw in stdout.splitlines():
        if not raw.strip().startswith(b"{"):
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        compact = json.dumps(event, separators=(",", ":")).lower()
        if any(fragment in compact for fragment in FORBIDDEN_EVENT_FRAGMENTS):
            if "assistant_message" not in compact and "token_count" not in compact:
                return True
    return False


def terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


async def reap_process(proc: asyncio.subprocess.Process) -> None:
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


class LocalCodexRunner:
    def __init__(self, settings: RunnerSettings) -> None:
        self.settings = settings
        self.ready = False
        self.reason = "initializing"
        self._init_lock = asyncio.Lock()

    @classmethod
    def from_app_settings(cls, app_settings: object) -> "LocalCodexRunner":
        default_model = getattr(app_settings, "codex_model", None)
        timeout = int(getattr(app_settings, "codex_request_timeout_seconds", 180))
        return cls(RunnerSettings.from_env(default_model, timeout))

    async def _refresh_ready(self) -> None:
        if self.ready:
            return
        async with self._init_lock:
            if self.ready:
                return
            try:
                await initialize_environment(self.settings)
            except Exception as exc:
                self.ready = False
                self.reason = classify_exception(exc)
                LOGGER.warning("runner initialization failed category=%s", self.reason)
                return
            self.ready = True
            self.reason = "ready"
            LOGGER.info("runner ready codex_version=%s", PINNED_CODEX_VERSION)

    async def status(self) -> dict[str, bool]:
        await self._refresh_ready()
        return {"ready": self.ready}

    async def execute(self, prompt: str, model: str | None = None, timeout: int | None = None) -> str:
        await self._refresh_ready()
        if not self.ready:
            if self.reason == "auth":
                raise RunnerError("auth")
            if self.reason == "safety":
                raise RunnerError("safety")
            if self.reason == "timeout":
                raise RunnerError("timeout")
            raise RunnerError("upstream")
        return await execute_codex(self.settings, prompt, model, timeout)


async def execute_codex(settings: RunnerSettings, prompt: str, model: str | None, timeout: int | None) -> str:
    effective_timeout = min(max(int(timeout or settings.request_timeout_seconds), 5), 900)
    child_home = settings.work_dir / ".empty-home"
    env = build_child_env(str(settings.codex_home), str(child_home))
    with tempfile.TemporaryDirectory(prefix="codex-provider-", dir="/tmp") as temp_dir:
        os.chmod(temp_dir, 0o700)
        output_path = Path(temp_dir) / "final.txt"
        fd = os.open(output_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.close(fd)
        command = build_codex_command(
            settings.codex_bin,
            str(settings.work_dir),
            str(output_path),
            model or settings.default_model,
        )
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(settings.work_dir),
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError as exc:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
            terminate_process_group(proc)
            await reap_process(proc)
            raise RunnerError("timeout") from exc
        finally:
            if proc.returncode is None:
                terminate_process_group(proc)
                await reap_process(proc)
        stdout = stdout[:STDOUT_LIMIT]
        stderr = stderr[:STDERR_LIMIT]
        if event_stream_has_forbidden_tools(stdout):
            raise RunnerError("safety")
        if proc.returncode != 0:
            raise RunnerError(classify_failure(proc.returncode or 1, stderr))
        try:
            final = output_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RunnerError("upstream") from exc
        if not final.strip():
            raise RunnerError("upstream")
        return final
