import pytest

from scripts.check_repo_hygiene import check_paths, is_allowed_codex_path


def test_codex_project_config_is_stageable():
    assert is_allowed_codex_path(".codex/config.toml")
    check_paths([".codex/config.toml"])


def test_codex_rules_files_are_stageable():
    assert is_allowed_codex_path(".codex/rules/default.rules")
    check_paths([".codex/rules/default.rules"])


@pytest.mark.parametrize(
    "path",
    [
        ".codex/auth.json",
        ".codex/history.jsonl",
        ".codex/sessions/2026/session.jsonl",
        ".codex/cache/state.json",
        ".codex/state.sqlite",
        ".codex/rules/nested/default.rules",
        ".codex/local-environment.json",
    ],
)
def test_codex_state_and_unknown_files_are_not_stageable(path):
    assert not is_allowed_codex_path(path)
    with pytest.raises(SystemExit):
        check_paths([path])


@pytest.mark.parametrize("path", [".env", "data/codex-home/auth.json", "codex-home/auth.json"])
def test_existing_forbidden_paths_stay_forbidden(path):
    with pytest.raises(SystemExit):
        check_paths([path])
