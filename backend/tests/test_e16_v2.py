"""E16 v2 (docs/design_agent_e16_v2.md): the Capability Router keyword layer and the A4
orchestration grammar. E16_legacy (test_e16.py) is untouched and unrelated to this file, per
the experiment's frozen-baseline rule."""

import json
from datetime import date, datetime, timedelta, timezone

from src import e16_v2 as v2
from src.llm_client import LlmError
from src.schemas import (
    ChatContext, ChatEmail, ChatRequest, DueList, RankedTaskList, ReviewQueue, TaskAction, TaskGroup, TaskRow,
    VesselView,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=CST)


class FakeRouterAndGenerate:
    """A single-purpose FakeLlm: returns router_answer for the E16_V2_ROUTER node and
    generate_answer (via complete_json or complete_chat) for E16_V2."""

    def __init__(self, router_answer=None, generate_answer=None, generate_turns=None):
        self.router_answer = router_answer
        self.generate_answer = generate_answer
        self.generate_turns = list(generate_turns or [])
        self.calls: list[tuple[str, str, dict]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key, json.loads(user)))
        if node == "E16_V2_ROUTER":
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
    return TaskRow(task_id=tid, vessel="VSL-12", voyage="V202", action=f"do {tid}", priority=priority,
                   statuses=["Action Required"], source_email_id=email, actions=[action])  # fmt: skip


def context():
    return ChatContext(
        tasks=RankedTaskList(groups=[TaskGroup(name="Action Required", items=[row("T1", 5, "E010")])]),
        dues=DueList(store_status="ok"),
        vessels=[VesselView(vessel_code="VSL-12")],
        review_queue=ReviewQueue(items=[], store_status="ok"),
        emails=[ChatEmail(email_id="E010", subject="REDEL NOTICE", sender="Charterer CPY-10", excerpt="x")],
    )  # fmt: skip


def ask(question, llm, run_tool=None):
    return v2.e16v2_answer_chat(ChatRequest(question=question), context(), llm, NOW, run_tool)


# --- A0 keyword layer (R1, R2, R3, R8) --------------------------------------------------------


def test_r1_invoice_question_is_a_code_level_capability_gap_no_model_call():
    llm = FakeRouterAndGenerate()
    answer = ask("还有哪些待付发票", llm)
    assert answer.retrieval_outcome == "capability_not_available"
    assert llm.calls == []  # never reached the router or generate model


def test_r3_bl_extraction_is_a_code_level_capability_gap():
    answer = ask("把所有bl（提单）帮我提取出来展示", FakeRouterAndGenerate())
    assert answer.retrieval_outcome == "capability_not_available"


def test_r2_distance_by_speed_is_a_code_level_capability_gap():
    answer = ask("从大连到天津，12节船速大概几天", FakeRouterAndGenerate())
    assert answer.retrieval_outcome == "capability_not_available"


def test_r8_read_status_paraphrase_family_is_a_code_level_capability_gap():
    for q in ["已经读了的呢", "有多少已经读了", "我已经读了多少邮件", "还有多少没读"]:
        answer = ask(q, FakeRouterAndGenerate())
        assert answer.retrieval_outcome == "capability_not_available", q


def test_pending_reply_is_not_a_false_positive_of_the_read_status_pattern():
    """"待回复" (pending reply) must not trip the read/unread keyword gap — it is a supported
    capability (open_tasks awaiting_reply), a real regression risk given both mention replying
    to or reading email."""
    assert v2._capability_gap_reason("哪些邮件待回复") is None


def test_a_due_date_question_is_not_a_false_positive_of_the_distance_pattern():
    """"多少天到期" must not trip the distance/travel-time gap — no knot/speed unit is present."""
    assert v2._capability_gap_reason("船租金还有多少天到期") is None


# --- Router-classified (R4, R5, R6, out_of_scope, a fourth capability gap the keywords miss) --


def test_r4_cost_allocation_is_decision_not_authorized():
    llm = FakeRouterAndGenerate(router_answer={
        "classification": "decision_not_authorized",
        "reason": "That needs a person's judgement, not the chat.",
    })  # fmt: skip
    answer = ask("根据这个CP，判断这笔费用应该Owners还是Charterers承担", llm)
    assert answer.retrieval_outcome == "decision_not_authorized"
    assert answer.text == "That needs a person's judgement, not the chat."
    assert answer.sources == []


def test_r6_operational_recommendation_is_decision_not_authorized_and_gives_no_recommendation():
    llm = FakeRouterAndGenerate(router_answer={
        "classification": "decision_not_authorized",
        "reason": "I can't recommend a port for this.",
    })  # fmt: skip
    answer = ask("这个航次适不适合安排UWI/UWC？在哪个港做比较方便？", llm)
    assert answer.retrieval_outcome == "decision_not_authorized"
    assert "Dampier" not in answer.text and "港" not in answer.text or "推荐" not in answer.text


def test_out_of_scope_is_classified_by_the_router_not_a_regex():
    llm = FakeRouterAndGenerate(router_answer={"classification": "out_of_scope", "reason": "小猫很可爱，但我帮不上忙。"})
    answer = ask("我养的猫今天很可爱", llm)
    assert answer.retrieval_outcome == "out_of_scope"


def test_a_capability_gap_the_keywords_miss_is_still_caught_by_the_router():
    """The registry's "port watch-outs" and "weather" categories have no code-level pattern
    (too open-ended to keyword-match safely) — the router must catch these on its own."""
    llm = FakeRouterAndGenerate(router_answer={
        "classification": "capability_not_available",
        "reason": "Weather conditions aren't tracked, only reported speed and consumption.",
    })  # fmt: skip
    answer = ask("xx（日期）船那天的天气怎么样", llm)
    assert answer.retrieval_outcome == "capability_not_available"


def test_a_malformed_router_answer_fails_closed_not_guessed_at():
    llm = FakeRouterAndGenerate(router_answer={"classification": "sort of maybe"})
    answer = ask("今天有什么要处理的", llm)
    assert answer.llm_status == "failed" and answer.text == v2.E16V2_FAILED


def test_router_failure_fails_closed():
    answer = ask("今天有什么要处理的", FakeRouterAndGenerate(router_answer=None))
    assert answer.llm_status == "failed"


# --- Supported path reaches the generate stage (R7, R9, baseline + tool loop) -----------------


def test_r7_pending_reply_reaches_generate_and_is_answered():
    llm = FakeRouterAndGenerate(
        router_answer={"classification": "supported", "reason": ""},
        generate_answer={"text": "1 email is waiting for a reply.",
                         "sources": [{"kind": "email", "id": "E010", "label": "REDEL NOTICE"}]},
    )  # fmt: skip
    answer = ask("哪些邮件待回复", llm)
    assert answer.retrieval_outcome is None
    assert [c[0] for c in llm.calls] == ["E16_V2_ROUTER", "E16_V2"]
    assert [(s.kind, s.id) for s in answer.sources] == [("email", "E010")]


def test_supported_question_with_no_data_for_this_instance():
    llm = FakeRouterAndGenerate(
        router_answer={"classification": "supported", "reason": ""},
        generate_answer={"text": "I don't have that vessel.", "sources": [], "outcome": "no_data"},
    )  # fmt: skip
    answer = ask("VSL-99现在什么情况", llm)
    assert answer.retrieval_outcome == "no_data"


def test_supported_question_uses_the_tool_loop_when_run_tool_is_given():
    found = ChatEmail(email_id="E099", subject="OFF-HIRE NOTICE", sender="CPY-09", excerpt="x")
    llm = FakeRouterAndGenerate(
        router_answer={"classification": "supported", "reason": ""},
        generate_turns=[
            {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E099"}}]},
            {"final": {"text": "It's an off-hire notice.",
                      "sources": [{"kind": "email", "id": "E099", "label": "OFF-HIRE NOTICE"}]}},
        ],  # fmt: skip
    )

    def run_tool(name, args):
        return found

    answer = ask("E099说的是什么", llm, run_tool)
    assert answer.retrieval_outcome is None
    assert [(s.kind, s.id) for s in answer.sources] == [("email", "E099")]
    assert [tc.name for tc in answer.tool_calls] == ["get_email"]
