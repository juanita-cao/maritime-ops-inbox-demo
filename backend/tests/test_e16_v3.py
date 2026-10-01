"""E16 v3 (docs/design_agent_e16_v3.md, owner-authored): Query Router + Routing Table +
per-query-type context slicing. E16_legacy and E16 v2 are both frozen and unrelated to this
file, per the experiment's frozen-baseline rule."""

import json
from datetime import date, datetime, timedelta, timezone

from src import e16_v3 as v3
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
        if node == "E16_V3_ROUTER":
            if self.router_answer is None:
                raise LlmError("no router answer scripted")
            return self.router_answer
        if self.generate_answer is None:
            raise LlmError("no generate answer scripted")
        return self.generate_answer

    def complete_chat(self, node, key, system, user, tools, turns):
        self.calls.append((node, key, json.loads(user)))
        return self.generate_turns.pop(0)


def row(tid, priority, email, statuses=("Action Required",), awaiting_reply=False):
    action = TaskAction(action_id=f"{tid}-A", task_id=tid, action_type="Check CP Terms", description=f"do {tid}",
                        priority=priority, due_type="Redelivery", due_date=date(2026, 8, 6), set_by="ai",
                        source_email_id=email, awaiting_reply=awaiting_reply)  # fmt: skip
    return TaskRow(task_id=tid, vessel="VSL-12", voyage="V202", action=f"do {tid}", priority=priority,
                   statuses=list(statuses), source_email_id=email, actions=[action])  # fmt: skip


def context(extra_groups=()):
    groups = [TaskGroup(name="Action Required", items=[row("T1", 5, "E010")])]
    groups.extend(extra_groups)
    return ChatContext(
        tasks=RankedTaskList(groups=groups),
        dues=DueList(store_status="ok"),
        vessels=[VesselView(vessel_code="VSL-12")],
        review_queue=ReviewQueue(items=[], store_status="ok"),
        emails=[ChatEmail(email_id="E010", subject="REDEL NOTICE", sender="Charterer CPY-10", excerpt="x")],
    )  # fmt: skip


def ask(question, llm, ctx=None, run_tool=None):
    return v3.e16v3_answer_chat(ChatRequest(question=question), ctx or context(), llm, NOW, run_tool)


# --- Routing table stop-states (R1-R6, R10) ---------------------------------------------------


def test_r1_invoice_routes_to_capability_not_available_via_the_table():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "INVOICE_STATUS_QUERY", "reason": "x"})
    answer = ask("还有哪些等待发票", llm)
    assert answer.retrieval_outcome == "capability_not_available"
    assert [c[0] for c in llm.calls] == ["E16_V3_ROUTER"]  # never reached generate


def test_r2_voyage_time_routes_to_capability_not_available():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "VOYAGE_TIME_QUERY", "reason": "x"})
    answer = ask("从大连到天津，12节船速大概几天", llm)
    assert answer.retrieval_outcome == "capability_not_available"


def test_r3_bl_document_routes_to_capability_not_available():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "BL_DOCUMENT_QUERY", "reason": "x"})
    answer = ask("把所有bl提取出来", llm)
    assert answer.retrieval_outcome == "capability_not_available"


def test_r4_cost_liability_routes_to_decision_not_authorized():
    llm = FakeRouterAndGenerate(router_answer={
        "query_type": "COST_LIABILITY_DECISION", "reason": "我无法决定费用由谁承担。",
    })  # fmt: skip
    answer = ask("根据这个CP，判断这笔费用应该Owners还是Charterers承担", llm)
    assert answer.retrieval_outcome == "decision_not_authorized"
    assert answer.text == "我无法决定费用由谁承担。"
    assert answer.sources == []


def test_r6_operation_recommendation_routes_to_decision_not_authorized():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "OPERATION_RECOMMENDATION", "reason": "x"})
    answer = ask("这个航次适不适合安排UWI/UWC？在哪个港做比较方便？", llm)
    assert answer.retrieval_outcome == "decision_not_authorized"


def test_r10_out_of_domain_routes_to_out_of_scope():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "OUT_OF_DOMAIN", "reason": "x"})
    answer = ask("今天天气怎么样", llm)
    assert answer.retrieval_outcome == "out_of_scope"


def test_an_unrecognised_query_type_fails_closed_not_guessed_at():
    llm = FakeRouterAndGenerate(router_answer={"query_type": "MADE_UP_TYPE", "reason": "x"})
    answer = ask("今天有什么要处理的", llm)
    assert answer.llm_status == "failed"


def test_router_failure_fails_closed():
    answer = ask("今天有什么要处理的", FakeRouterAndGenerate(router_answer=None))
    assert answer.llm_status == "failed"


# --- Per-query-type context slicing (the R1/R3 structural fix) --------------------------------


def test_vessel_fact_query_context_has_no_review_queue_or_emails_to_pad_with():
    """§12 M5: the generate call for VESSEL_FACT_QUERY must not even receive review_queue or
    emails — nothing irrelevant is available to cite, unlike legacy which always sent everything."""
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "VESSEL_FACT_QUERY", "reason": ""},
        generate_answer={"text": "No current facts for VSL-12.", "sources": []},
    )  # fmt: skip
    ask("VSL-12现在什么情况", llm)
    sent_context = llm.calls[1][2]["context"]
    assert set(sent_context.keys()) == {"vessels"}


def test_pending_reply_query_context_is_pre_filtered_in_code():
    """§12 M9: PENDING_REPLY_QUERY's context is already filtered to Waiting-for-Reply tasks in
    code — the model is never shown the full open_tasks list, only the pending-reply slice."""
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "PENDING_REPLY_QUERY", "reason": ""},
        generate_answer={"text": "1 item is waiting for a reply.",
                         "sources": [{"kind": "email", "id": "E010", "label": "REDEL NOTICE"}]},
    )  # fmt: skip
    ctx = context(extra_groups=[TaskGroup(name="Waiting for Reply",
                                          items=[row("T2", 3, "E020", statuses=("Waiting for Reply",))])])  # fmt: skip
    answer = ask("哪些邮件待回复", llm, ctx)
    sent_context = llm.calls[1][2]["context"]
    assert set(sent_context.keys()) == {"pending_reply_total", "pending_reply_tasks"}
    assert sent_context["pending_reply_total"] == 1
    assert [t["task_id"] for t in sent_context["pending_reply_tasks"]] == ["T2"]
    assert answer.retrieval_outcome is None


def test_open_task_query_never_receives_review_queue():
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "OPEN_TASK_QUERY", "reason": ""},
        generate_answer={"text": "1 task.", "sources": []},
    )  # fmt: skip
    ask("目前待办事项", llm)
    sent_context = llm.calls[1][2]["context"]
    assert set(sent_context.keys()) == {"open_tasks_total", "open_tasks"}


def test_work_queue_query_gets_both_lists():
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "WORK_QUEUE_QUERY", "reason": ""},
        generate_answer={"text": "1 task and 0 review items.", "sources": []},
    )  # fmt: skip
    ask("今天有什么要处理的", llm)
    sent_context = llm.calls[1][2]["context"]
    assert set(sent_context.keys()) == {"open_tasks_total", "open_tasks", "review_queue_total", "review_queue"}


# --- Tool-eligible micro-DEPs (M6-M8, M10) still use the real tool loop ------------------------


def test_email_lookup_uses_the_tool_loop_when_run_tool_is_given():
    found = ChatEmail(email_id="E099", subject="OFF-HIRE NOTICE", sender="CPY-09", excerpt="x")
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "EMAIL_LOOKUP", "reason": ""},
        generate_turns=[
            {"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E099"}}]},
            {"final": {"text": "It's an off-hire notice.",
                      "sources": [{"kind": "email", "id": "E099", "label": "OFF-HIRE NOTICE"}]}},
        ],  # fmt: skip
    )

    def run_tool(name, args):
        return found

    answer = ask("E099说的是什么", llm, run_tool=run_tool)
    assert answer.retrieval_outcome is None
    assert [(s.kind, s.id) for s in answer.sources] == [("email", "E099")]
    assert [tc.name for tc in answer.tool_calls] == ["get_email"]


def test_r11_vessel_not_in_fleet_is_no_data():
    llm = FakeRouterAndGenerate(
        router_answer={"query_type": "VESSEL_FACT_QUERY", "reason": ""},
        generate_answer={"text": "I don't have that vessel.", "sources": [], "outcome": "no_data"},
    )  # fmt: skip
    answer = ask("VSL-99现在什么情况", llm)
    assert answer.retrieval_outcome == "no_data"
