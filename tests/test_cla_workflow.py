"""Guards for the Contributor License Agreement check (.github/workflows/cla.yml).

The dual-licence model relies on every contributor signing .github/CLA-1.0.md.
A signature is evidence of agreement to one exact text, so published agreements
are pinned by hash: changing the terms means a new version file, sign phrase,
and signatures path, never an edit in place. These tests also keep the sign
phrase consistent across the workflow and docs, and keep privileged workflows
from running pull-request code.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO / ".github" / "workflows"
_CLA_WORKFLOW = _WORKFLOWS / "cla.yml"
_DOC_PREFIX = "https://github.com/debpalash/VoiceStudio/blob/main/"
# Triggers that run with a write token and repository secrets, even on fork PRs.
_PRIVILEGED_TRIGGERS = {"pull_request_target", "issue_comment", "workflow_run"}
# SHA-256 of each published agreement with LF line endings. Never update a hash:
# publish a new version file instead, so existing signatures keep their text.
_PUBLISHED_AGREEMENTS = {
    ".github/CLA-1.0.md": "569bb24e423559c53ecdedd50bffce2a340635d033d25acf4de84fe6b140d2d2",
    ".github/CCLA-1.0.md": "8365d168305c76cce632c42cd822b2dc599f1417f37d99016ece0179c031904b",
}


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


def test_sign_phrase_matches_workflow_filter_and_docs():
    step = _cla_step()["with"]
    phrase = step["custom-pr-sign-comment"]
    assert f"'{phrase}'" in _load(_CLA_WORKFLOW)["jobs"]["cla"]["if"]
    document = _REPO / step["path-to-document"].removeprefix(_DOC_PREFIX)
    for path in (document, _REPO / ".github" / "CONTRIBUTING.md"):
        assert phrase in path.read_text(encoding="utf-8"), path


def test_document_sign_phrase_and_signature_store_share_one_version():
    step = _cla_step()["with"]
    (doc_version,) = re.findall(r"CLA-(\d+)\.(\d+)\.md$", step["path-to-document"])
    assert f"CLA {doc_version[0]}.{doc_version[1]} " in step["custom-pr-sign-comment"]
    assert step["path-to-signatures"] == f"signatures/v{doc_version[0]}/cla.json"


def test_published_agreements_are_never_edited():
    for path, expected in _PUBLISHED_AGREEMENTS.items():
        text = (_REPO / path).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert hashlib.sha256(text.encode()).hexdigest() == expected, (
            f"{path} changed. Publish the new terms as a new version file instead."
        )


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
