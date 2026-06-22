import pytest

from scripts.image_tags import build_candidate_tag, sanitize_ref_name, validate_image_tag


def test_build_candidate_tag_uses_branch_and_short_sha():
    tag = build_candidate_tag("feature/pi-node2 smoke", "ABCDEF1234567890")
    assert tag == "codex-cli-provider-dev-feature-pi-node2-smoke-abcdef123456"


def test_build_candidate_tag_truncates_long_refs_to_docker_limit():
    tag = build_candidate_tag("feature/" + "x" * 200, "0123456789abcdef")
    assert len(tag) == 128
    assert tag.endswith("-0123456789ab")


def test_sanitize_ref_name_has_stable_fallback():
    assert sanitize_ref_name("///") == "ref"


def test_validate_release_tag_accepts_project_semver():
    assert validate_image_tag("codex-cli-provider-0.1.2", "release") == "codex-cli-provider-0.1.2"
    assert validate_image_tag("codex-cli-provider-0.1.2-rc.1", "release") == "codex-cli-provider-0.1.2-rc.1"


@pytest.mark.parametrize(
    "tag,kind",
    [
        ("latest", "any"),
        ("v0.1.2", "release"),
        ("codex-cli-provider-0.1.2+build", "release"),
        ("codex-cli-provider-0.1.2", "candidate"),
        ("codex-cli-provider-dev-feature", "release"),
    ],
)
def test_validate_image_tag_rejects_invalid_tags(tag, kind):
    with pytest.raises(SystemExit):
        validate_image_tag(tag, kind)
