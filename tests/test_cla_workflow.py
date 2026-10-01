"""Guards for the Contributor License Agreement check (.github/workflows/cla.yml).

The dual-licence model relies on every contributor signing .github/CLA.md. These
tests keep the signing phrase consistent between the workflow and the docs, keep
the linked agreement present, and keep privileged workflows from running
pull-request code.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO / ".github" / "workflows"
_CLA_WORKFLOW = _WORKFLOWS / "cla.yml"
_DOC_PREFIX = "https://github.com/debpalash/VoiceStudio/blob/main/"
# Triggers that run with a write token and repository secrets, even on fork PRs.
_PRIVILEGED_TRIGGERS = {"pull_request_target", "issue_comment", "workflow_run"}


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML reads the bare `on:` key as boolean True.
    data["on"] = data.pop(True, data.get("on")) or {}
    return data


def _cla_step() -> dict:
    steps = _load(_CLA_WORKFLOW)["jobs"]["cla"]["steps"]
    (step,) = [s for s in steps if s.get("uses", "").startswith("contributor-assistant/github-action@")]
    return step


def test_cla_action_is_pinned_to_a_commit():
    ref = _cla_step()["uses"].split("@", 1)[1]
    assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), ref


def test_cla_document_link_points_at_a_file_in_this_repo():
    url = _cla_step()["with"]["path-to-document"]
    assert url.startswith(_DOC_PREFIX), url
    assert (_REPO / url.removeprefix(_DOC_PREFIX)).is_file(), url


def test_sign_phrase_matches_workflow_filter_and_contributing():
    phrase = _cla_step()["with"]["custom-pr-sign-comment"]
    job_filter = _load(_CLA_WORKFLOW)["jobs"]["cla"]["if"]
    assert f"'{phrase}'" in job_filter
    assert phrase in (_REPO / ".github" / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_signatures_are_not_committed_to_main():
    assert _cla_step()["with"]["branch"] not in {"main", "master"}


def test_allowlist_covers_maintainer_and_bots():
    allowlist = {item.strip() for item in _cla_step()["with"]["allowlist"].split(",")}
    assert {"debpalash", "*[bot]"} <= allowlist


def test_privileged_workflows_never_run_pull_request_code():
    for path in sorted(_WORKFLOWS.glob("*.y*ml")):
        workflow = _load(path)
        triggers = set(workflow["on"]) if isinstance(workflow["on"], (dict, list)) else {workflow["on"]}
        if not triggers & _PRIVILEGED_TRIGGERS:
            continue
        for name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                assert not step.get("uses", "").startswith("actions/checkout@"), f"{path.name}:{name} checks out code"
                assert "run" not in step, f"{path.name}:{name} runs a shell step"
