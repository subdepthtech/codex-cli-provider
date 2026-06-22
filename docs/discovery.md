# Discovery Record

Status: operator-approved single-container Docker execution retry. The service now runs the HTTP wrapper and Codex CLI in one root container with a dedicated bind-mounted project `CODEX_HOME`.

Date: 2026-06-21

## Official Sources Checked

- OpenAI Codex manual fetched from `https://developers.openai.com/codex/codex-manual.md`.
- OpenAI Codex CLI page: `https://developers.openai.com/codex/cli`.
- Official repository: `https://github.com/openai/codex`.
- Official release metadata: `https://github.com/openai/codex/releases/tag/rust-v0.141.0`.
- Obsidian LLM Wiki source: `https://github.com/green-dalii/obsidian-llm-wiki`, commit `4512f93`.

## Codex CLI Version

Installed local CLI:

- `codex-cli 0.141.0`
- Official latest release observed: `rust-v0.141.0`, published 2026-06-18.

Pinned Linux artifacts discovered from the official GitHub release:

- AMD64: `codex-x86_64-unknown-linux-musl.tar.gz`
  - SHA-256: `f1e2bf9fa0ba6eb82119d621b6b71bc38edd33c06dc2867b31a027052358957d`
- ARM64: `codex-aarch64-unknown-linux-musl.tar.gz`
  - SHA-256: `8c9f31811d659fcc17c5f1a21bc0971984469c9e3a63c2b39b61cc7694f3a101`

The official repository README says each archive contains a single platform-named executable that can be renamed to `codex`.

## Verified CLI Flags And Behavior

- Model selection: global and `exec` flag `-m, --model <MODEL>`.
- Sandbox selection for generated shell commands: `-s, --sandbox <SANDBOX_MODE>`.
  - Values: `read-only`, `workspace-write`, `danger-full-access`.
- Approval policy: global flag `-a, --ask-for-approval <APPROVAL_POLICY>`; in the installed 0.141.0 CLI it must be placed before `exec`.
  - Values include `untrusted`, `on-request`, `never`; `on-failure` is deprecated.
  - `never` means no approval prompts; failures are returned to the model.
- Stdin prompt: `codex exec [PROMPT]`; if prompt is omitted or `-`, instructions are read from stdin.
- Noninteractive ephemeral execution: `codex exec --ephemeral`.
- JSONL events: `codex exec --json`.
- Final response file: `codex exec -o, --output-last-message <FILE>`.
- Non-JSON final response behavior: official docs state progress streams to stderr and only the final agent message prints to stdout.
- Working directory: `-C, --cd <DIR>`.
- User config bypass: `codex exec --ignore-user-config`.
- Rules bypass: `codex exec --ignore-rules`.
- Git check: `codex exec` requires a Git repository unless `--skip-git-repo-check` is used.
- Dangerous bypass flags exist and must not be used:
  - `--dangerously-bypass-approvals-and-sandbox`
  - `--yolo` alias documented in official CLI reference.

`codex sandbox linux --help` is not a current subcommand in 0.141.0. The supported helper form is `codex sandbox [OPTIONS] [COMMAND]...` with `-P, --permissions-profile <NAME>` and `-C, --cd <DIR>`.

## Authentication And State

- `CODEX_HOME` selects the Codex state root. The directory must already exist.
- Common state includes `config.toml`, `auth.json` when file-backed credential storage is used, logs, sessions, skills, and package metadata.
- `cli_auth_credentials_store = "file"` stores credentials in `auth.json` under `CODEX_HOME`.
- `forced_login_method = "chatgpt"` is documented.
- Device login is supported with `codex login --device-auth`.
- Browser login can fail in headless environments; OpenAI docs recommend device-code auth first.
- File-backed ChatGPT sessions refresh tokens automatically during use, so the dedicated `CODEX_HOME` must be writable if token refresh is required.
- Official docs describe copying `auth.json` for headless/CI workflows, but this project must not copy a normal user `~/.codex`; any login flow must use a dedicated project auth home.
- This project uses only device-based ChatGPT login in the dedicated project auth home.

## Tool And Persistence Controls

Relevant feature flags observed with `codex features list` in 0.141.0:

- Shell execution: `shell_tool` stable, default `true`.
- Unified execution: `unified_exec` stable, default `true`.
- JavaScript REPL: `js_repl` and `js_repl_tools_only` removed, default `false`.
- Web/search: global `--search`; config `web_search = "disabled" | "cached" | "live"`; legacy search flags are removed/deprecated.
- MCP: `[mcp_servers]` table; tool/MCP feature flags include `enable_mcp_apps`, `tool_call_mcp_elicitation`.
- Apps/connectors: `apps` stable, default `true`.
- Plugins: `plugins` stable, default `true`; `remote_plugin` under development.
- Hooks: `hooks` stable, default `true`.
- Skills/dependency install: `skill_mcp_dependency_install` stable, default `true`.
- Memories: `memories` experimental, default `false`; `[memories]` controls use/generation when enabled.
- Remote control: `remote_control` removed; app-server and cloud commands still exist.
- Multi-agent: `multi_agent` stable, default `true`; `multi_agent_v2` under development.
- Shell snapshot: `shell_snapshot` stable, default `true`.
- Browser/computer tools: `browser_use`, `browser_use_external`, and `computer_use` stable, default `true`.

Relevant settings:

- History persistence: `[history] persistence = "save-all" | "none"`.
- Analytics: `[analytics] enabled = true | false`.
- Feedback: `[feedback] enabled = true | false`.
- Telemetry: `[otel] exporter`, `trace_exporter`, `metrics_exporter`, `log_user_prompt`.
- Plaintext log directory: `log_dir`; setting it explicitly enables `codex-tui.log`.
- Child shell environment: `[shell_environment_policy] inherit`, `include_only`, `exclude`, `set`, `ignore_default_excludes`.
- Login-shell control: `allow_login_shell = false`.

## Credential Isolation Probe

The built-in `:read-only` permission profile can read a canary file placed under the isolated `CODEX_HOME`, so it is insufficient.

A custom profile extending `:read-only` with an explicit filesystem deny for the dedicated `CODEX_HOME` prevented reading the canary in a direct `codex sandbox -P <profile>` probe on the host.

This mitigation still requires the Linux sandbox itself to start correctly
inside the target Docker runtime. It is not used by the current
`danger-full-access` container posture; in that posture, Docker mount
minimization is the primary boundary.

## Docker Sandbox Discovery

A temporary Docker probe previously used:

- Non-root user `10001:10001`.
- Normal Docker bridge network.
- No host network.
- No privileged mode.
- No added capabilities in the earlier Bubblewrap probe.
- `--cap-drop ALL`.
- `--security-opt no-new-privileges:true`.
- Read-only root filesystem.
- Tmpfs for `/tmp`, `/home/app`, and `/srv/work`.
- Official Codex 0.141.0 ARM64 standalone artifact with SHA-256 verification.

Result:

- Without system Bubblewrap, `codex sandbox` could not start because no `bwrap` executable or bundled helper was available next to the Codex executable.
- With Debian `bubblewrap` installed, `codex sandbox` still failed under the required Docker restrictions because Bubblewrap could not create a user namespace.

This blocked the earlier unprivileged split-container plan: the current validated Docker runtime could not run the Codex Linux sandbox inside an ordinary unprivileged container without weakening the requested container restrictions.

Root-only Docker settings were also insufficient on this host because
`codex sandbox` still failed with Bubblewrap namespace creation errors. The
current implementation intentionally uses `sandbox_mode = "danger-full-access"`
inside a Docker container with minimal bind mounts, read-only root filesystem,
dropped capabilities, only `DAC_OVERRIDE` and `FOWNER` added back for dedicated
bind-mount access, no Docker socket, no host home, and no broad host paths. Do
not silently escalate further by enabling privileged mode, adding `SYS_ADMIN`,
using unconfined seccomp/AppArmor, host networking, `--yolo`, or bypassing
wrapper bearer auth.

## Obsidian LLM Wiki Contract

Source inspected: `green-dalii/obsidian-llm-wiki` commit `4512f93`.

- Provider setting includes `Custom OpenAI-Compatible`.
- Base URL should include `/v1`; the plugin appends `/chat/completions` and `/models` directly.
- `/v1/models` response expected: OpenAI-style `{ "data": [{ "id": "..." }] }`.
- Model IDs containing `:` or `/` are filtered out for the generic custom provider.
- `/chat/completions` body fields observed:
  - `model`
  - `messages`
  - `max_tokens`
  - `max_completion_tokens` for `gpt-5*` model IDs
  - `stream`
  - optional `temperature`
  - optional `repetition_penalty`
  - optional `thinking`
  - optional `reasoning_effort`
  - optional `chat_template_kwargs`
- System content is sent as a leading `system` message.
- Query mode prefers streaming and falls back to non-streaming if streaming fails.
- SSE parser accepts OpenAI-style `data:` events, reads `choices[0].delta.content`, optional `reasoning_content`, optional `finish_reason`, and stops on `data: [DONE]`.
- Default page generation concurrency is `3`; default batch delay is `500` ms.
- Retry behavior: HTTP 5xx/429 and network-like errors retry up to 2 attempts with exponential backoff.
- Embeddings endpoint is not required for the OpenAI-compatible provider path inspected here.
- The observed lint analysis path sends a normal `POST` to `/chat/completions`
  with `model`, `max_tokens: 4000`, and one large user prompt. It does not use
  OpenAI tools, `tool_choice`, `functions`, `parallel_tool_calls`, or the
  Responses API.
- LLM Wiki's schema option affects prompt text only for this path. CORS
  `OPTIONS` requests may appear after a primary 400, but they are diagnostic
  noise rather than the failing lint call.
- Large lint prompts may need the wrapper limits raised from the repo defaults
  (`MAX_REQUEST_BODY_BYTES=262144`, `MAX_TOTAL_TEXT_CHARS=80000`) to the hard
  caps validated in the homelab deployment (`2000000` bytes and `500000` text
  characters). Reproduce size behavior with synthetic text, not note bodies.

## Decision

The original all-in-one Docker design was blocked under the required
unprivileged container restrictions, and root-only Docker settings still failed
the Codex Bubblewrap sandbox. The implemented design now uses an
operator-approved single root container that includes the local HTTP wrapper and
Codex execution, backed by the same dedicated auth directory, no-prompt approval
policy, and `danger-full-access` inside the Docker boundary.

Do not weaken Docker beyond the current posture by enabling privileged mode,
adding `SYS_ADMIN`, using unconfined seccomp/AppArmor, host networking, mounting
the Docker socket, mounting host home directories, or mounting the Obsidian
vault. The current posture adds back only `DAC_OVERRIDE` and `FOWNER` after
`cap_drop: ALL` so container root can access the dedicated host-owned bind
mounts.
