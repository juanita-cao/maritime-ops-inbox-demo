"""Playbooks (docs/design_agent_e16_v7.md 7): an operator's procedure for a kind of question, kept
as one markdown file per procedure under kb/playbooks/ with a YAML header.

The router may pick one by id; the chosen playbook is put into the reasoning prompt, and the answer
reports each step as done / missing / not_applicable. Only `approved` playbooks are used, unless
E16_INCLUDE_DRAFT_PLAYBOOKS=1 (the owner's review runs). The loader is strict: an invalid file
stops the service at startup, like the knowledge base.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

PRIMITIVES = ("Select", "Extract", "Detect", "Compare", "Transform", "Generate", "Allocation", "Ranking")


class PlaybookStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    primitive: Literal[PRIMITIVES]  # type: ignore[valid-type]
    text: str


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    when: str
    mode: Literal["evidence_reasoning", "proposal_reasoning", "domain_knowledge", "hybrid"]  # how this procedure is answered
    status: Literal["draft", "approved"]
    source: str
    requires: list[str] = []
    steps: list[PlaybookStep]
    body: str = ""

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", v):
            raise ValueError("id must be a lowercase slug")
        return v

    @field_validator("steps")
    @classmethod
    def _unique_steps(cls, v: list[PlaybookStep]) -> list[PlaybookStep]:
        ids = [s.id for s in v]
        if not v or len(set(ids)) != len(ids):
            raise ValueError("steps must be present and have unique ids")
        return v


class PlaybookError(Exception):
    pass


def parse_playbook(text: str, name: str = "playbook") -> Playbook:
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        raise PlaybookError(f"{name}: no YAML header")
    try:
        header = yaml.safe_load(m.group(1)) or {}
        return Playbook(**header, body=m.group(2).strip())
    except (yaml.YAMLError, ValidationError, TypeError) as exc:
        raise PlaybookError(f"{name}: {exc}") from exc


def load_playbooks(folder: Path) -> dict[str, Playbook]:
    """Every playbook file, validated; an invalid file or a repeated id raises."""
    out: dict[str, Playbook] = {}
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.md")):
        if path.name.startswith(("._", "README")):
            continue
        pb = parse_playbook(path.read_text(encoding="utf-8"), path.name)
        if pb.id != path.stem:
            raise PlaybookError(f"{path.name}: id {pb.id!r} must equal the file name")
        if pb.id in out:
            raise PlaybookError(f"{path.name}: repeated id {pb.id}")
        out[pb.id] = pb
    return out


def usable(playbooks: dict[str, Playbook]) -> dict[str, Playbook]:
    """The playbooks the assistant may use now."""
    drafts = os.getenv("E16_INCLUDE_DRAFT_PLAYBOOKS") == "1"
    return {k: p for k, p in playbooks.items() if p.status == "approved" or drafts}


def router_menu(playbooks: dict[str, Playbook]) -> str:
    """The lines the router sees; empty when there is nothing to choose from."""
    if not playbooks:
        return ""
    lines = "\n".join(f"- {p.id}: {p.when}" for p in playbooks.values())
    return (
        "PLAYBOOKS\nWhen the question matches one of these procedures, return its id in \"playbook\"; otherwise null. "
        "A procedure needs the records read, so never pair it with deterministic; its own mode is applied by the system.\n" + lines + "\n\n"
    )


def prompt_block(pb: Playbook) -> str:
    """The PLAYBOOK section of the reasoning prompt."""
    steps = "\n".join(f"{s.id} [{s.primitive}] {s.text}" for s in pb.steps)
    needs = ("Evidence this procedure needs: " + "; ".join(pb.requires) + "\n") if pb.requires else ""
    marker = " (draft)" if pb.status == "draft" else ""
    return (
        f"PLAYBOOK {pb.id}{marker}: {pb.title}\n"
        "Follow these steps in order. Work each step from the records you read; where the records do not hold "
        "what a step needs, that step is missing — say what is missing. Report every step in \"steps\" "
        "({\"step_id\", \"status\": done|missing|not_applicable, \"note\": one short line, \"evidence_ids\": ids you read}). "
        "A step is done only if you read the evidence for it. A Generate step that writes an email is done only when the "
        "email is in \"draft\" (plain text, placeholders for what is not known), not in \"answer\".\n"
        "If you mention this procedure in the answer, call it the operation guide (操作指引 in Chinese), never \"playbook\" or 作业指引.\n"
        f"{needs}{steps}\n\nGUIDANCE\n{pb.body}\n"
    )


@dataclass(frozen=True)
class StepResult:
    step_id: str
    primitive: str
    text: str
    status: str
    note: str
    evidence_ids: list[str]


def reconcile_steps(pb: Playbook, reported: list[dict], read_ids: set[str], draft_written: bool = False) -> list[StepResult]:
    """Merge the model's step report with the playbook's definition, in the playbook's order. A
    step the model did not report is missing; `done` without evidence the model actually read
    becomes missing (design 7.3)."""
    by_id = {str(r.get("step_id")): r for r in reported if isinstance(r, dict)}
    out = []
    for s in pb.steps:
        r = by_id.get(s.id, {})
        status = r.get("status") if r.get("status") in ("done", "missing", "not_applicable") else "missing"
        ids = [e for e in r.get("evidence_ids") or [] if isinstance(e, str)]
        note = str(r.get("note") or "").strip()
        if status == "done" and not (ids and all(e in read_ids for e in ids)):
            status = "missing"
            note = (note + " " if note else "") + "(no evidence that was actually read)"
        if s.primitive == "Generate" and re.search(r"\bemail\b", s.text, re.I):
            status, note = ("done", note) if draft_written else ("missing", note or "no draft written")
        if s.id not in by_id:
            note = note or "not reported"
        out.append(StepResult(s.id, s.primitive, s.text, status, note, ids))
    return out
