"""E16 v6 (docs/design_agent_e16_v6.md): answer shape, follow-ups, router voting, grounding check.
v1-v5.1 are frozen and unrelated to this file."""

import json
from datetime import date, datetime, timedelta, timezone

from src import e16_v6 as v6
from src.llm_client import LlmError
from src.schemas import (
    ChatContext, ChatEmail, ChatRequest, ChatTurn, DueList, FactRow, RankedTaskList, ReviewQueue, TaskAction,
    TaskGroup, TaskRow, VesselView,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=CST)


class FakeLlm:
    """routes: one dict for every router sample, or a list (one per sample)."""

    def __init__(self, routes=None, answer=None, turns=None, revise=None):
        self.routes = routes
        self.answer = answer
        self.turns = list(turns or [])
        self.revise = revise
        self.calls: list[tuple[str, str, dict]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key, json.loads(user)))
        if node == "E16_V6_ROUTER":
            if self.routes is None:
                raise LlmError("no route")
            return self.routes[int(key[-1])] if isinstance(self.routes, list) else self.routes
        if node == "E16_V6_REVISE":
            return self.revise
        if self.answer is None:
            raise LlmError("no answer")
        return self.answer

    def complete_chat(self, node, key, system, user, tools, turns):
        self.calls.append((node, key, json.loads(user)))
        return self.turns.pop(0)


def context():
    action = TaskAction(action_id="T1-A", task_id="T1", action_type="Check CP Terms", description="do T1", priority=3,
                        due_type="Hire", due_date=date(2026, 8, 6), set_by="ai", source_email_id="E054")  # fmt: skip
    row = TaskRow(task_id="T1", vessel="VSL-02", voyage="V203", action="Get survey quotation", priority=3,
                  statuses=["Approval Required"], source_email_id="E054", actions=[action])  # fmt: skip
    fact = FactRow(fact_key="rob_vlsfo", value="451.024 MT", event_time=NOW, source_email_id="E053", superseded=False)
    return ChatContext(
        tasks=RankedTaskList(groups=[TaskGroup(name="Approval Required", items=[row])]),
        dues=DueList(store_status="ok"), vessels=[VesselView(vessel_code="VSL-02", facts=[fact])],
        review_queue=ReviewQueue(items=[], store_status="ok"),
        emails=[ChatEmail(email_id="E046", subject="M/V VSL-02//ROB", sender="Master",
                          excerpt="Arrival Discharge Port Distance 1400nm including 80nm ECA")],
    )  # fmt: skip


def ask(question, llm, history=None, run_tool=None):
    req = ChatRequest(question=question, history=[ChatTurn(**h) for h in history or []])
    return v6.e16v6_answer_chat(req, context(), llm, NOW, run_tool)


def route(mode, **kw):
    return {"execution_mode": mode, "deterministic_intent": None, "answer_size": "standard", **kw}


# --- router self-consistency ----------------------------------------------------------------


def test_router_majority_wins_and_is_traced():
    llm = FakeLlm(routes=[route("out_of_scope"), route("deterministic", deterministic_intent="open_tasks"),
                          route("deterministic", deterministic_intent="open_tasks")])  # fmt: skip
    answer = ask("目前待办事项", llm)
    assert answer.execution_mode == "deterministic"
    assert answer.reasoning_trace[0].startswith("Router: 2/3 samples agree on deterministic/open_tasks")


def test_router_all_samples_failing_fails_closed():
    assert ask("目前待办事项", FakeLlm()).llm_status == "failed"


# --- answer shape -----------------------------------------------------------------------------


def test_short_answer_with_company_distance_is_one_line_plus_source():
    """v5.1 #18: code labelled a distance read from E046 as a general estimate."""
    llm = FakeLlm(routes=route("domain_knowledge", answer_size="short"),
                  answer={"answer": "按你们记录的航程约 5 天。", "details": "E046：1400nm including 80nm ECA",
                          "sources": [{"kind": "email", "id": "E046"}],
                          "passage_estimate": {"distance_nm": 1400, "speed_kn": 12, "distance_source": "E046"}})  # fmt: skip
    answer = ask("从Dampier到Newcastle，12节船速大概几天", llm)
    assert "≈ 4.9 天纯航行（1,400 nm ÷ 12 kn = 117 h；距离出自 E046）" in answer.text
    assert "一般估算" not in answer.text and "verified routing distance" not in answer.text
    assert answer.text.endswith("来源：E046")
    assert "一般航运知识部分不是公司记录" in answer.details  # the long disclaimer lives in details


def test_answer_over_budget_moves_to_details():
    long = "\n".join(f"- 第{i}条" for i in range(1, 9))
    llm = FakeLlm(routes=route("domain_knowledge", answer_size="short"), answer={"answer": long, "sources": []})
    answer = ask("Newcastle港要注意什么", llm)
    assert answer.text.count("第") == 4
    assert answer.details.startswith("- 第5条")
    assert any("moved to details" in t for t in answer.reasoning_trace)


def test_proposal_conclusion_in_answer_full_contract_in_details():
    llm = FakeLlm(routes=route("proposal_reasoning", answer_size="detailed"),
                  answer={"answer": "E045 没有费用条款。", "sources": [{"kind": "email", "id": "E046"}],
                          "proposal": {"conclusion": "Owners 先行承担", "basis": [{"point": "船东询价", "source": "E046"}],
                                       "counter_evidence": ["还船相关"], "missing_information": ["CP 条款"]}})  # fmt: skip
    answer = ask("这笔费用Owners还是Charterers承担", llm)
    assert answer.text.startswith("**初步建议：**Owners 先行承担（建议，需复核）")
    assert "缺失信息：" in answer.details and "- 船东询价 [E046]" in answer.details
    assert "缺失信息" not in answer.text


def test_grounding_check_flags_numbers_not_in_anything_read():
    llm = FakeLlm(routes=route("evidence_reasoning"),
                  answer={"answer": "到港 ROB VLSFO 451.024 MT，LSMGO 99.9 MT（E046）。", "sources": []})
    answer = ask("VSL-02 到港存油", llm)
    assert "99.9" in answer.details and "451.024" not in answer.details
    assert any("Grounding check (code): 1 item" in t for t in answer.reasoning_trace)


def test_draft_keeps_the_answer_to_one_short_budget():
    llm = FakeLlm(routes=route("evidence_reasoning", answer_size="standard"),
                  answer={"answer": "草稿如下。\n另：金额未核对。\n多余1\n多余2\n多余3", "draft": "Dear PER-33, hire [amount] due today."})
    answer = ask("起草一封给租家的邮件告知租金今天到期", llm)
    assert answer.draft.startswith("Dear PER-33")
    assert len(answer.text.split("\n")) <= 4


# --- follow-ups -------------------------------------------------------------------------------


PREV = [{"role": "user", "text": "Newcastle港要注意什么问题"},
        {"role": "assistant", "text": "\n".join(["ETA Newcastle P/S 8/4 1500LT（E053）", "约 8/6 还船（E052）"] +
                                                [f"- 通用建议 {i}" for i in range(12)])}]  # fmt: skip


def test_too_long_is_a_follow_up_rewrite_not_out_of_scope():
    """Screenshot 1: "太长了，有用信息也不多啊" was answered with "这是对上一条回复的反馈…"."""
    llm = FakeLlm(routes=route("follow_up", answer_size="short"),
                  revise={"answer": "ETA Newcastle P/S 8/4 1500LT（E053）；约 8/6 还船（E052）。", "details": ""})
    answer = ask("太长了，有用信息也不多啊", llm, history=PREV)
    assert answer.execution_mode == "follow_up"
    assert len(answer.text) < len(PREV[1]["text"])
    assert [s.id for s in answer.sources] == ["E053", "E052"]
    assert not any(c[0] == "E16_V6" for c in llm.calls)  # no new retrieval


def test_follow_up_cannot_add_facts():
    llm = FakeLlm(routes=route("follow_up", answer_size="short"),
                  revise={"answer": "ETA 8/4（E053），吃水 12.5 m。", "details": ""})
    answer = ask("简单点", llm, history=PREV)
    assert "12.5" in answer.details


def test_out_of_scope_in_a_conversation_prefers_a_follow_up_sample():
    llm = FakeLlm(routes=[route("out_of_scope"), route("out_of_scope"), route("follow_up")],
                  revise={"answer": "ETA 8/4（E053）。", "details": ""})
    assert ask("有用信息也不多啊", llm, history=PREV).execution_mode == "follow_up"


def test_follow_up_without_history_asks_for_a_question():
    llm = FakeLlm(routes=route("follow_up"))
    assert "请先问" in ask("太长了", llm).text


def test_standalone_question_is_used_for_the_answer():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="vessel_facts", standalone_question="VSL-02 的燃油还有多少"),
                  answer={"summary": "VSL-02：", "items": [{"label": "ROB VLSFO", "value": "451.024 MT", "source": "E053"}]})
    answer = ask("那燃油呢", llm, history=PREV)
    assert "451.024 MT" in answer.text
    assert any(t.startswith("Standalone question: VSL-02") for t in answer.reasoning_trace)


def test_the_previous_answer_is_part_of_the_recording_key():
    a, b = FakeLlm(routes=route("out_of_scope", reason="x")), FakeLlm(routes=route("out_of_scope", reason="x"))
    ask("太长了", a, history=PREV)
    ask("太长了", b, history=[PREV[0], {"role": "assistant", "text": "another answer"}])
    assert a.calls[0][1] != b.calls[0][1]


def test_an_intent_put_in_execution_mode_is_repaired_not_failed():
    llm = FakeLlm(routes={"execution_mode": "open_tasks", "deterministic_intent": None, "answer_size": "short"})
    answer = ask("目前待办事项", llm)
    assert answer.execution_mode == "deterministic" and "共 1 项" in answer.text


def test_pure_passage_question_can_leave_the_answer_to_code():
    llm = FakeLlm(routes=route("domain_knowledge", answer_size="short"),
                  answer={"answer": "", "sources": [{"kind": "email", "id": "E046"}],
                          "passage_estimate": {"distance_nm": 1400, "speed_kn": 12, "distance_source": "E046"}})
    answer = ask("从Dampier到Newcastle，12节船速大概几天", llm)
    assert answer.text.splitlines() == ["≈ 4.9 天纯航行（1,400 nm ÷ 12 kn = 117 h；距离出自 E046）", "来源：E046"]


def test_a_draft_object_is_rendered_as_an_email():
    llm = FakeLlm(routes=route("evidence_reasoning", answer_size="short"),
                  answer={"answer": "草稿如下。", "draft": {"subject": "Hire due", "body": "Dear PER-33,\nHire is due today."}})
    assert ask("起草一封给租家的邮件告知租金今天到期", llm).draft == "Subject: Hire due\n\nDear PER-33,\nHire is due today."


def test_simple_steps_use_the_fast_model_and_reasoning_uses_the_main_one():
    fast = FakeLlm(routes=route("deterministic", deterministic_intent="open_tasks"))
    main = FakeLlm()
    assert "共 1 项" in v6.e16v6_answer_chat(ChatRequest(question="目前待办事项"), context(), main, NOW, fast_llm=fast).text
    assert main.calls == [] and fast.calls[0][0] == "E16_V6_ROUTER"

    fast = FakeLlm(routes=route("evidence_reasoning"))
    main = FakeLlm(answer={"answer": "CPY-14（E046）。", "sources": [{"kind": "email", "id": "E046"}]})
    v6.e16v6_answer_chat(ChatRequest(question="VSL-02在Newcastle港代理是哪家"), context(), main, NOW, fast_llm=fast)
    assert [c[0] for c in main.calls] == ["E16_V6"]


def test_reasoning_context_is_slimmed_to_the_named_vessel():
    ctx = context().model_copy(update={"emails": [
        ChatEmail(email_id="E001", subject="MV VSL-01 report", sender="Master", excerpt="x" * 500),
        ChatEmail(email_id="E002", subject="MV VSL-02 report", sender="Master", excerpt="y" * 500)]})
    llm = FakeLlm(routes=route("evidence_reasoning"), answer={"answer": "ok", "sources": []})
    v6.e16v6_answer_chat(ChatRequest(question="VSL-02 的报告"), ctx, llm, NOW)
    sent = next(c[2] for c in llm.calls if c[0] == "E16_V6")["context"]
    assert [e["email_id"] for e in sent["emails"]] == ["E002"] and len(sent["emails"][0]["excerpt"]) == 160


def test_payment_status_question_is_not_sent_to_the_due_list():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="dues"),
                  answer={"answer": "没有待付发票：E060 为租家已付第 30 期租金（E060）。", "sources": []})
    answer = ask("VSL-01还有哪些待付发票", llm)
    assert answer.execution_mode == "evidence_reasoning"
    assert any("payment-status" in t for t in answer.reasoning_trace)


def test_passage_distance_source_is_listed_as_a_source():
    llm = FakeLlm(routes=route("domain_knowledge", answer_size="short"),
                  answer={"answer": "", "sources": [],
                          "passage_estimate": {"distance_nm": 1400, "speed_kn": 12, "distance_source": "E046"}})
    answer = ask("从Dampier到Newcastle，12节船速大概几天", llm)
    assert [s.id for s in answer.sources] == ["E046"] and answer.text.endswith("来源：E046")
