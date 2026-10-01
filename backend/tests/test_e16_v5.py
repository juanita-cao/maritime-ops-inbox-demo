"""E16 v5 (docs/design_agent_e16_v5.md): Execution Router + deterministic SaaS queries + a
reasoning executor with labelled knowledge sources. v1-v4 are frozen and unrelated to this file."""

import json
from datetime import date, datetime, timedelta, timezone

from src import e16_v5 as v5
from src.llm_client import LlmError
from src.schemas import (
    ChatContext, ChatEmail, ChatRequest, DueList, DueRow, FactRow, RankedTaskList, ReviewQueue, TaskAction,
    TaskGroup, TaskRow, VesselView,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=CST)


class FakeLlm:
    def __init__(self, route=None, answer=None, turns=None):
        self.route = route
        self.answer = answer
        self.turns = list(turns or [])
        self.calls: list[tuple[str, dict]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, json.loads(user)))
        if node == "E16_V5_ROUTER":
            if self.route is None:
                raise LlmError("no route scripted")
            return self.route
        if self.answer is None:
            raise LlmError("no answer scripted")
        return self.answer

    def complete_chat(self, node, key, system, user, tools, turns):
        self.calls.append((node, json.loads(user)))
        return self.turns.pop(0)


def row(tid, priority, email, statuses, awaiting=False):
    action = TaskAction(action_id=f"{tid}-A", task_id=tid, action_type="Check CP Terms", description=f"do {tid}",
                        priority=priority, due_type="Hire", due_date=date(2026, 8, 6), set_by="ai",
                        source_email_id=email, awaiting_reply=awaiting)  # fmt: skip
    return TaskRow(task_id=tid, vessel="VSL-12", voyage="V202", action=f"do {tid}", priority=priority,
                   statuses=statuses, source_email_id=email, actions=[action])  # fmt: skip


def context(rows=None):
    rows = rows if rows is not None else [row("T1", 5, "E010", ["Approval Required"])]
    groups = {}
    for r in rows:
        for st in r.statuses:
            groups.setdefault(st, []).append(r)
    fact = FactRow(fact_key="rob_vlsfo", value="420 MT", event_time=NOW, source_email_id="E070", superseded=False)
    return ChatContext(
        tasks=RankedTaskList(groups=[TaskGroup(name=k, items=v) for k, v in groups.items()]),
        dues=DueList(items=[DueRow(task_id="T1", action_id="T1-A", vessel="VSL-12", action="pay hire",
                                   due_type="Hire", due_date=date(2026, 8, 6), priority=4)], store_status="ok"),
        vessels=[VesselView(vessel_code="VSL-12", facts=[fact])],
        review_queue=ReviewQueue(items=[], store_status="ok"),
        emails=[ChatEmail(email_id="E010", subject="REDEL NOTICE", sender="Charterer CPY-10", excerpt="x")],
    )  # fmt: skip


def ask(question, llm, ctx=None, run_tool=None):
    return v5.e16v5_answer_chat(ChatRequest(question=question), ctx or context(), llm, NOW, run_tool)


# --- Deterministic Red tests: the questions v4 routed out_of_scope or answered by guessing ----


def test_open_tasks_is_rendered_in_code_without_a_second_llm_call():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "open_tasks"})
    answer = ask("目前待办事项", llm)
    assert [c[0] for c in llm.calls] == ["E16_V5_ROUTER"]
    assert answer.execution_mode == "deterministic"
    assert "共 1 项" in answer.text and "E010" in answer.text
    assert ("task", "T1") in [(s.kind, s.id) for s in answer.sources]


def test_pending_reply_never_counts_approval_required():
    """R15 in v1/v2/v4: an Approval Required task was listed as 'waiting for reply'."""
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "pending_reply"})
    answer = ask("哪些邮件待回复", llm)
    assert "当前没有" in answer.text
    assert answer.sources == []
    assert answer.retrieval_outcome == "no_data"


def test_pending_reply_lists_waiting_rows_and_caps_at_five_with_a_total():
    rows = [row(f"T{i}", 3, f"E0{i:02d}", ["Waiting for Reply"]) for i in range(7)]
    rows.append(row("TA", 5, "E099", ["Approval Required"]))
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "pending_reply"})
    answer = ask("哪些邮件待回复", llm, context(rows))
    assert "共 7 项" in answer.text and "另有 2 项" in answer.text
    assert "E099" not in answer.text
    assert answer.text.count("\n- ") == 5


def test_awaiting_reply_flag_on_an_action_also_counts():
    rows = [row("T1", 3, "E001", ["Action Required"], awaiting=True)]
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "pending_reply"})
    assert "共 1 项" in ask("哪些邮件待回复", llm, context(rows)).text


def test_english_question_gets_an_english_deterministic_answer():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "open_tasks"})
    assert ask("What is on my plate?", llm).text.startswith("Open tasks: 1.")


def test_vessel_facts_model_only_sees_the_named_vessel_slice():
    llm = FakeLlm(
        route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"},
        answer={"text": "- ROB VLSFO: 420 MT\n天气数据在当前记录中没有找到。",
                "sources": [{"kind": "email", "id": "E070"}, {"kind": "email", "id": "E999"}],
                "evidence_status": "partial"},
    )  # fmt: skip
    answer = ask("VSL-12 油耗和天气", llm)
    present = llm.calls[1][1]
    assert set(present["context"]) == {"vessels"}  # no tasks, reviews or emails to pad with
    assert [s.id for s in answer.sources] == ["E070"]  # E999 was never in the slice
    assert answer.evidence_status == "partial"


def test_unknown_vessel_is_no_matching_data_without_asking_the_model():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"})
    answer = ask("VSL-99 什么时候到港", llm)
    assert answer.evidence_status == "no_matching_data"
    assert [c[0] for c in llm.calls] == ["E16_V5_ROUTER"]


def test_vessel_code_directly_followed_by_chinese_is_still_found():
    """Live run 1: "VSL-12船..." missed with \\b, because 船 is a word character."""
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"},
                  answer={"text": "- ROB VLSFO: 420 MT", "sources": [], "evidence_status": "sufficient"})
    assert ask("VSL-12船存燃油还有多少", llm).evidence_status == "sufficient"


def test_dues_slice_is_filtered_to_the_named_vessel():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "dues"},
                  answer={"text": "下一笔租金 due 是 2026-08-06。", "sources": [{"kind": "task", "id": "T1"}],
                          "evidence_status": "sufficient"})  # fmt: skip
    assert ask("VSL-12租金下一个due是哪天", llm).sources[0].id == "T1"
    assert llm.calls[1][1]["context"]["dues_total"] == 1


def test_no_dues_for_the_vessel_is_rendered_in_code_as_none_not_unavailable():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "dues"})
    answer = ask("VSL-11租金下一个due是哪天", llm)
    assert "没有任何 due" in answer.text and len(llm.calls) == 1
    assert answer.retrieval_outcome == "no_data"


# --- Router contract ------------------------------------------------------------------------


def test_out_of_scope_stops_after_the_router():
    llm = FakeLlm(route={"execution_mode": "out_of_scope", "reason": "这个我帮不上。"})
    answer = ask("我的猫可爱吗", llm)
    assert answer.execution_mode == "out_of_scope" and answer.retrieval_outcome == "out_of_scope"
    assert len(llm.calls) == 1


def test_deterministic_without_a_known_intent_fails_closed():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "whatever"})
    assert ask("目前待办事项", llm).llm_status == "failed"


def test_router_failure_fails_closed():
    assert ask("目前待办事项", FakeLlm()).llm_status == "failed"


# --- Reasoning executor ---------------------------------------------------------------------


def test_domain_knowledge_is_answered_not_refused_and_authority_is_fixed_in_code():
    llm = FakeLlm(route={"execution_mode": "domain_knowledge", "deterministic_intent": None},
                  answer={"text": "一般航运操作上：确认泊位/锚地……", "sources": [], "evidence_status": "partial",
                          "reasoning_trace": ["Applied general practice (S2)"]})  # fmt: skip
    answer = ask("Newcastle港要注意什么", llm)
    assert answer.execution_mode == "domain_knowledge"
    assert answer.capability_authority == "supported_l1"
    assert answer.reasoning_trace == ["Applied general practice (S2)"]


def test_hybrid_and_proposal_are_l2():
    for mode in ("hybrid", "proposal_reasoning"):
        llm = FakeLlm(route={"execution_mode": mode},
                      answer={"text": "初步建议……需人工复核。", "sources": [], "evidence_status": "partial"})
        assert ask("V202 在哪个港安排 UWI/UWC", llm).capability_authority == "supported_l2"


def test_trace_starts_with_the_code_verified_tool_calls():
    found = ChatEmail(email_id="E051", subject="CTM - NEWCASTLE", sender="Port Agent CPY-14", excerpt="x")
    llm = FakeLlm(
        route={"execution_mode": "evidence_reasoning"},
        turns=[{"tool_calls": [{"name": "search_emails", "arguments": {"vessel": "VSL-12"}}]},
               {"final": {"text": "租家代理是 CPY-14。", "sources": [{"kind": "email", "id": "E051"}],
                          "evidence_status": "sufficient", "reasoning_trace": ["Extracted agent from E051"]}}],
    )  # fmt: skip
    answer = ask("VSL-12在Newcastle港租家代理是哪家", llm, run_tool=lambda n, a: [found])
    assert answer.reasoning_trace[0].startswith("Tool search_emails")
    assert answer.reasoning_trace[1] == "Extracted agent from E051"
    assert [s.id for s in answer.sources] == ["E051"]


def test_relevance_gate_drops_an_email_about_another_vessel_and_flags_the_answer():
    """Live run 1, R14: E055 (VSL-11 at Rizhao) was cited as proof of VSL-12's cranes."""
    other = {"email_id": "E055", "subject": "RE: MV VSL-11 DISCHG", "vessel": "VSL-11"}
    llm = FakeLlm(
        route={"execution_mode": "evidence_reasoning"},
        turns=[{"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E055"}}]},
               {"final": {"text": "VSL-12 用岸吊。", "sources": [{"kind": "email", "id": "E055"}],
                          "evidence_status": "sufficient"}}],
    )  # fmt: skip
    answer = ask("VSL-12装/卸货作业用船吊还是岸吊", llm, run_tool=lambda n, a: other)
    assert answer.sources == []
    assert "相关性检查" in answer.text and answer.evidence_status == "partial"
    assert any("Relevance gate" in step for step in answer.reasoning_trace)


def test_passage_time_is_computed_in_code_not_by_the_model():
    """Live run 1, R18: the model wrote 720 nm / 12 kn = 6 days (it is 2.5)."""
    llm = FakeLlm(route={"execution_mode": "domain_knowledge"},
                  answer={"text": "以下为粗略估算。", "sources": [], "evidence_status": "partial",
                          "passage_estimate": {"distance_nm": 720, "speed_kn": 12}})  # fmt: skip
    answer = ask("从Dampier到Newcastle，12节船速大概几天", llm)
    assert "60 小时 ≈ 2.5 天" in answer.text and "verified routing distance" in answer.text
    assert "来源说明：未引用公司记录" in answer.text


def test_an_implausible_passage_estimate_is_ignored():
    llm = FakeLlm(route={"execution_mode": "domain_knowledge"},
                  answer={"text": "x", "sources": [], "passage_estimate": {"distance_nm": "far", "speed_kn": 12}})
    assert "粗略估算" not in ask("A到B几天", llm).text


def test_l2_answer_always_carries_the_human_review_line():
    llm = FakeLlm(route={"execution_mode": "proposal_reasoning"},
                  answer={"text": "初步建议：更可能由 Charterers 承担。", "sources": []})
    assert "复核" in ask("这笔费用Owners还是Charterers承担", llm).text


def test_proposal_is_rendered_in_code_with_every_contract_part():
    llm = FakeLlm(route={"execution_mode": "proposal_reasoning"},
                  answer={"text": "E010 是租家的还船通知。", "sources": [{"kind": "email", "id": "E010"}],
                          "evidence_status": "sufficient",
                          "proposal": {"conclusion": "更可能由 Charterers 承担",
                                       "basis": [{"point": "租家提前还船", "source": "E010"}],
                                       "counter_evidence": ["条款原文未见"], "missing_information": ["CP 条款"]}})  # fmt: skip
    answer = ask("这笔费用Owners还是Charterers承担", llm)
    for part in ("**初步建议：**更可能由 Charterers 承担", "- 租家提前还船 [E010]", "**反向可能", "**缺失信息：**", "复核"):
        assert part in answer.text
    assert answer.evidence_status == "sufficient"


def test_a_proposal_without_a_retrieved_source_is_marked_weak_and_downgraded():
    """Live run 2, R2: a bare "费用应由Charterers承担" with no basis at all."""
    llm = FakeLlm(route={"execution_mode": "proposal_reasoning"},
                  answer={"text": "", "sources": [], "evidence_status": "sufficient",
                          "proposal": {"conclusion": "应由 Charterers 承担",
                                       "basis": [{"point": "租家保留权利", "source": "E777"}]}})  # fmt: skip
    answer = ask("这笔费用Owners还是Charterers承担", llm)
    assert "依据不足" in answer.text and "[无可核对出处]" in answer.text
    assert answer.evidence_status == "missing_required_evidence"


def test_vessel_facts_heading_without_values_gets_the_locked_rows_from_code():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"},
                  answer={"text": "VSL-12 当前存量如下：", "sources": [{"kind": "email", "id": "E070"}]})
    answer = ask("VSL-12船存燃油还有多少", llm)
    assert "rob_vlsfo: 420 MT" in answer.text and "[E070]" in answer.text


def test_named_port_is_searched_in_company_records_by_code_before_the_model_answers():
    hit = {"email_id": "E051", "subject": "M/V VSL-12//CTM - NEWCASTLE", "vessel": "VSL-12"}
    asked: list[dict] = []
    llm = FakeLlm(route={"execution_mode": "domain_knowledge", "search_terms": ["Newcastle", "VSL-12"]},
                  turns=[{"final": {"text": "根据你们自己的记录：E051……", "sources": [{"kind": "email", "id": "E051"}]}}])
    answer = ask("Newcastle港要注意什么问题", llm, run_tool=lambda n, a: asked.append(a) or [hit])
    assert asked == [{"text": "Newcastle", "limit": 5}]  # vessel codes are not text-searched
    assert llm.calls[1][1]["s1_prefetch"]["Newcastle"][0]["email_id"] == "E051"
    assert [s.id for s in answer.sources] == ["E051"]
    assert answer.reasoning_trace[0].startswith("Tool search_emails") and "S1 first" in answer.reasoning_trace[0]


# --- [AMENDMENT v5.1] -------------------------------------------------------------------------


def ask51(question, llm, ctx=None, run_tool=None):
    return v5.e16v5_answer_chat(ChatRequest(question=question), ctx or context(), llm, NOW, run_tool, revision="5.1")


def test_v51_router_guard_overrides_out_of_scope_for_a_shipping_question():
    llm = FakeLlm(route={"execution_mode": "out_of_scope", "reason": "不涉及航运操作"},
                  answer={"text": "记录里没有找到 VSL-12 的吊机信息。", "sources": [], "evidence_status": "no_matching_data"})
    answer = ask51("VSL-12装/卸货作业用船吊还是岸吊", llm)
    assert answer.execution_mode == "evidence_reasoning"
    assert answer.reasoning_trace[0].startswith("Router guard (code)")


def test_v51_router_guard_leaves_small_talk_out_of_scope():
    llm = FakeLlm(route={"execution_mode": "out_of_scope", "reason": "这个我帮不上。"})
    assert ask51("我的猫可爱吗", llm).execution_mode == "out_of_scope"


def test_frozen_v50_keeps_its_behaviour():
    llm = FakeLlm(route={"execution_mode": "out_of_scope", "reason": "不涉及航运操作"})
    assert ask("VSL-12装/卸货作业用船吊还是岸吊", llm).execution_mode == "out_of_scope"


def test_v51_vessel_facts_renders_verified_items_and_missing_parts():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"},
                  answer={"summary": "VSL-12 油耗如下：",
                          "items": [{"label": "ROB VLSFO", "value": "420 MT", "time": "7/30", "source": "E070"},
                                    {"label": "ROB LSMGO", "value": "999 MT", "time": "7/30", "source": "E070"}],
                          "missing": ["天气"]})  # fmt: skip
    answer = ask51("VSL-12这几天的油耗和天气", llm)
    assert "- ROB VLSFO：420 MT（7/30） [E070]" in answer.text
    assert "999" not in answer.text  # not in the cited source: dropped by code
    assert "- 天气：当前记录中没有找到" in answer.text
    assert answer.evidence_status == "partial"
    assert any("dropped 1 item" in t for t in answer.reasoning_trace)


def test_v51_vessel_facts_falls_back_to_code_list_when_model_gives_nothing():
    llm = FakeLlm(route={"execution_mode": "deterministic", "deterministic_intent": "vessel_facts"},
                  answer={"summary": "如下：", "items": []})
    assert "rob_vlsfo: 420 MT" in ask51("VSL-12 船存燃油", llm).text


def test_an_invalid_evidence_status_is_dropped():
    llm = FakeLlm(route={"execution_mode": "evidence_reasoning"},
                  answer={"text": "ok", "sources": [], "evidence_status": "made up"})
    assert ask("检查E055的问题", llm).evidence_status is None
