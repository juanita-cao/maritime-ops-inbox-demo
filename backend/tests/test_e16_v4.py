"""E16 v4 (docs/design_agent_e16_v4.md, owner-authored): Authority Router + Reasoning stage
with a two-dimensional outcome. E16_legacy, E16 v2 and E16 v3 are all frozen and unrelated to
this file, per the experiment's frozen-baseline rule."""

import json
from datetime import date, datetime, timedelta, timezone

from src import e16_v4 as v4
from src.llm_client import LlmError
from src.schemas import (
    ChatContext, ChatEmail, ChatRequest, DueList, RankedTaskList, ReviewQueue, TaskAction, TaskGroup, TaskRow,
    VesselView,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=CST)


class FakeRouterAndGenerate:
    def __init__(self, router_answer=None, generate_answer=None, generate_turns=None):
        self.router_answer = router_answer
        self.generate_answer = generate_answer
        self.generate_turns = list(generate_turns or [])
        self.calls: list[tuple[str, str, dict]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key, json.loads(user)))
        if node == "E16_V4_ROUTER":
            if self.router_answer is None:
                raise LlmError("no router answer scripted")
            return self.router_answer
        if self.generate_answer is None:
            raise LlmError("no generate answer scripted")
        return self.generate_answer

    def complete_chat(self, node, key, system, user, tools, turns):
        self.calls.append((node, key, json.loads(user)))
        return self.generate_turns.pop(0)


def row(tid, priority, email):
    action = TaskAction(action_id=f"{tid}-A", task_id=tid, action_type="Check CP Terms", description=f"do {tid}",
                        priority=priority, due_type="Redelivery", due_date=date(2026, 8, 6), set_by="ai",
                        source_email_id=email)  # fmt: skip
    return TaskRow(task_id=tid, vessel="VSL-02", voyage="V202", action=f"do {tid}", priority=priority,
                   statuses=["Action Required"], source_email_id=email, actions=[action])  # fmt: skip


def context():
    return ChatContext(
        tasks=RankedTaskList(groups=[TaskGroup(name="Action Required", items=[row("T1", 5, "E010")])]),
        dues=DueList(store_status="ok"),
        vessels=[VesselView(vessel_code="VSL-02")],
        review_queue=ReviewQueue(items=[], store_status="ok"),
        emails=[ChatEmail(email_id="E010", subject="REDEL NOTICE", sender="Charterer CPY-10", excerpt="x")],
    )  # fmt: skip


def ask(question, llm, run_tool=None):
    return v4.e16v4_answer_chat(ChatRequest(question=question), context(), llm, NOW, run_tool)


def test_out_of_scope_stops_before_any_reasoning_call():
    llm = FakeRouterAndGenerate(router_answer={"authority": "out_of_scope", "reason": "小猫很可爱，但我帮不上忙。"})
    answer = ask("我养的猫今天很可爱", llm)
    assert answer.capability_authority == "out_of_scope"
    assert answer.retrieval_outcome == "out_of_scope"
    assert [c[0] for c in llm.calls] == ["E16_V4_ROUTER"]


def test_an_unrecognised_authority_fails_closed():
    llm = FakeRouterAndGenerate(router_answer={"authority": "sort of maybe", "reason": ""})
    answer = ask("今天有什么要处理的", llm)
    assert answer.llm_status == "failed"


def test_router_failure_fails_closed():
    answer = ask("今天有什么要处理的", FakeRouterAndGenerate(router_answer=None))
    assert answer.llm_status == "failed"


# --- L1: unstructured-evidence reasoning is allowed, unlike v2/v3's registry gate -------------


def test_port_agent_from_email_text_is_l1_not_blocked_by_a_registry():
    """The R8 regression this rebuild targets: v2/v3 refused this outright even though email
    E051 explicitly states the answer. v4 must be able to search + extract + cite it."""
    found = ChatEmail(email_id="E051", subject="CTM - NEWCASTLE", sender="Port Agent CPY-14", excerpt="x")
    llm = FakeRouterAndGenerate(
        router_answer={"authority": "supported_l1", "reason": ""},
        generate_turns=[
            {"tool_calls": [{"name": "search_emails", "arguments": {"vessel": "VSL-02", "event_type": "Port Agency / Port Costs (DA)"}}]},
            {"final": {"text": "Email E051 names CPY-14 as the port agent at Newcastle.",
                      "sources": [{"kind": "email", "id": "E051", "label": "CTM - NEWCASTLE"}],
                      "evidence_status": "sufficient"}},
        ],  # fmt: skip
    )

    def run_tool(name, args):
        return [found]

    answer = ask("VSL-02在Newcastle港租家代理是哪家", llm, run_tool)
    assert answer.capability_authority == "supported_l1"
    assert answer.evidence_status == "sufficient"
    assert answer.retrieval_outcome is None  # sufficient is a real answer, not a refusal
    assert [(s.kind, s.id) for s in answer.sources] == [("email", "E051")]


def test_missing_required_evidence_is_distinct_from_no_data():
    """§9's key example: SUPPORTED_L2 + MISSING_REQUIRED_EVIDENCE ("I need the CP") must not
    collapse into a blanket refusal — retrieval_outcome has no v1-v3 equivalent for this, so it
    stays None; only capability_authority/evidence_status carry the nuance."""
    llm = FakeRouterAndGenerate(
        router_answer={"authority": "supported_l2", "reason": ""},
        generate_answer={"text": "I can assess who is more likely to bear this cost, but I need the relevant CP clauses first.",
                         "sources": [], "evidence_status": "missing_required_evidence"},
    )  # fmt: skip
    answer = ask("根据这个CP，判断这笔费用应该Owners还是Charterers承担", llm)
    assert answer.capability_authority == "supported_l2"
    assert answer.evidence_status == "missing_required_evidence"
    assert answer.retrieval_outcome is None


def test_no_matching_data_maps_to_retrieval_outcome_for_comparability():
    llm = FakeRouterAndGenerate(
        router_answer={"authority": "supported_l1", "reason": ""},
        generate_answer={"text": "I don't have that vessel.", "sources": [], "evidence_status": "no_matching_data"},
    )  # fmt: skip
    answer = ask("VSL-99现在什么情况", llm)
    assert answer.evidence_status == "no_matching_data"
    assert answer.retrieval_outcome == "no_data"  # cross-version comparability mapping


def test_retrieval_limit_reached_is_code_forced_over_the_models_own_label():
    llm = FakeRouterAndGenerate(
        router_answer={"authority": "supported_l1", "reason": ""},
        generate_turns=[
            {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E001"}}]},
            {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E002"}}]},
            {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E003"}}]},
            {"final": {"text": "I could not find enough.", "sources": [], "evidence_status": "partial"}},
        ],  # fmt: skip
    )

    def run_tool(name, args):
        return ChatEmail(email_id="E00x", subject="s", sender="CPY-01", excerpt="x")

    answer = ask("Tell me about E001, E002 and E003", llm, run_tool)
    assert answer.evidence_status == "retrieval_limit_reached"
    assert answer.retrieval_outcome == "retrieval_limit_reached"


def test_an_invalid_evidence_status_is_dropped_not_trusted():
    llm = FakeRouterAndGenerate(
        router_answer={"authority": "supported_l1", "reason": ""},
        generate_answer={"text": "ok", "sources": [], "evidence_status": "the model made this up"},
    )  # fmt: skip
    answer = ask("今天有什么要处理的", llm)
    assert answer.evidence_status is None
