"""Playbooks (docs/design_agent_e16_v7.md 7): the loader is strict, only approved ones are used, the
router menu and prompt block are built from the files, and a step report is reconciled in code."""

from pathlib import Path

import pytest

from src import playbooks as p

REPO = Path(__file__).resolve().parents[2]

GOOD = """---
id: demo-one
title: Demo
when: A demo question.
mode: evidence_reasoning
status: approved
source: test
steps:
  - {id: s1, primitive: Select, text: "Read it."}
  - {id: s2, primitive: Generate, text: "Say it."}
---
Guidance text.
"""


def test_the_shipped_playbooks_are_valid_and_complete():
    books = p.load_playbooks(REPO / "kb" / "playbooks")
    assert set(books) == {"uwi-uwc-arrangement", "document-crosscheck", "cost-allocation", "hire-next-due",
                          "port-arrival-checklist"}  # fmt: skip
    assert all(b.status in ("draft", "approved") and b.steps and b.source for b in books.values())


def test_parse_rejects_bad_files():
    for bad, why in [("no header", "no YAML header"),
                     (GOOD.replace("primitive: Select", "primitive: Magic"), "primitive"),
                     (GOOD.replace("id: demo-one", "id: Demo One"), "slug"),
                     (GOOD.replace("status: approved", "status: maybe"), "status"),
                     (GOOD.replace("id: s2", "id: s1"), "unique"),
                     (GOOD.replace("source: test\n", ""), "source"),
                     (GOOD.replace("mode: evidence_reasoning\n", ""), "mode")]:
        with pytest.raises(p.PlaybookError, match=why):
            p.parse_playbook(bad)


def test_the_file_name_must_equal_the_id(tmp_path):
    (tmp_path / "other-name.md").write_text(GOOD, encoding="utf-8")
    with pytest.raises(p.PlaybookError, match="must equal the file name"):
        p.load_playbooks(tmp_path)
    (tmp_path / "other-name.md").unlink()
    (tmp_path / "demo-one.md").write_text(GOOD, encoding="utf-8")
    (tmp_path / "README.md").write_text("not a playbook", encoding="utf-8")
    (tmp_path / "._demo-one.md").write_bytes(b"\x00\x05")
    assert list(p.load_playbooks(tmp_path)) == ["demo-one"]


def test_only_approved_playbooks_are_used_unless_drafts_are_switched_on(monkeypatch):
    approved, draft = p.parse_playbook(GOOD), p.parse_playbook(GOOD.replace("approved", "draft").replace("demo-one", "demo-two"))
    books = {approved.id: approved, draft.id: draft}
    monkeypatch.delenv("E16_INCLUDE_DRAFT_PLAYBOOKS", raising=False)
    assert list(p.usable(books)) == ["demo-one"]
    monkeypatch.setenv("E16_INCLUDE_DRAFT_PLAYBOOKS", "1")
    assert list(p.usable(books)) == ["demo-one", "demo-two"]


def test_router_menu_and_prompt_block():
    pb = p.parse_playbook(GOOD)
    assert p.router_menu({}) == ""
    assert "- demo-one: A demo question." in p.router_menu({"demo-one": pb})
    block = p.prompt_block(pb)
    assert "PLAYBOOK demo-one: Demo" in block and "s1 [Select] Read it." in block and "Guidance text." in block
    assert "(draft)" in p.prompt_block(p.parse_playbook(GOOD.replace("approved", "draft")))


def test_step_report_is_reconciled_in_the_playbooks_order_and_done_needs_read_evidence():
    pb = p.parse_playbook(GOOD)
    got = p.reconcile_steps(pb, [{"step_id": "s2", "status": "done", "note": "ok", "evidence_ids": ["E999"]}], {"E046"})
    assert [(r.step_id, r.status) for r in got] == [("s1", "missing"), ("s2", "missing")]
    assert got[0].note == "not reported" and "no evidence that was actually read" in got[1].note
    ok = p.reconcile_steps(pb, [{"step_id": "s1", "status": "done", "evidence_ids": ["E046"]},
                                {"step_id": "s2", "status": "not_applicable"}, {"step_id": "zz", "status": "done"}], {"E046"})  # fmt: skip
    assert [(r.step_id, r.status) for r in ok] == [("s1", "done"), ("s2", "not_applicable")]
    assert p.reconcile_steps(pb, [{"step_id": "s1", "status": "weird"}], set())[0].status == "missing"


def test_an_email_generating_step_is_done_only_with_a_draft():
    pb = p.parse_playbook(GOOD.replace('text: "Say it."', 'text: "Draft the inquiry email."'))
    assert p.reconcile_steps(pb, [], set(), draft_written=False)[1].status == "missing"
    assert p.reconcile_steps(pb, [], set(), draft_written=True)[1].status == "done"
    assert "done only when the email is in \"draft\"" in p.prompt_block(pb)
