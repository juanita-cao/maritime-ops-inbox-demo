"""E16 v7 M0 (docs/design_agent_e16_v7.md 4): structured output, evidence contract, output scan,
vessel grounding. v1-v6 are frozen and unrelated to this file. Every id number below is invented."""

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src import e16_v7 as v7
from src.llm_client import LlmError
from src.schemas import (
    ChatContext, ChatEmail, ChatRequest, ChatTurn, DueList, FactRow, RankedTaskList, ReviewQueue, TaskAction,
    TaskGroup, TaskRow, VesselView,
)  # fmt: skip

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=CST)
E046_TEXT = "Please kindly find the ROB calculation: 3. Arrival Discharge Port Distance 1400nm including 80nm ECA"


class FakeLlm:
    def __init__(self, routes=None, answers=None, turns=None, revise=None, present=None, verify=None):
        self.verify = verify
        self.systems: dict[str, str] = {}
        self.users: dict[str, dict] = {}
        self.routes = routes
        self.answers = list(answers or [])  # one per E16_V7 complete_json call (first, then the repair)
        self.turns = list(turns or [])
        self.revise = revise
        self.present = present
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, node, key, system, user):
        self.calls.append((node, key))
        self.systems[node] = system
        try:
            self.users[node] = json.loads(user)
        except ValueError:  # the repair prompt appends text to the JSON
            self.users[node] = {}
        if node == "E16_V7_ROUTER":
            if self.routes is None:
                raise LlmError("no route")
            return self.routes[int(key[-1])] if isinstance(self.routes, list) else self.routes
        if node == "E16_V6_REVISE":
            return self.revise
        if node in ("E16_V5_PRESENT", "E16_V7_PRESENT"):
            return self.present
        if node == "E16_V7_VERIFY":
            return self.verify(key) if callable(self.verify) else self.verify
        return self.answers.pop(0)

    def complete_chat(self, node, key, system, user, tools, turns):
        self.calls.append((node, key))
        self.systems[node] = system
        self.users[node] = json.loads(user)
        return self.turns.pop(0)


def full(**over):
    """A complete AnswerOut object, as strict mode would return it."""
    base = {"answer": "", "details": "", "sources": [], "evidence": [], "draft": None, "evidence_status": "sufficient",
            "reasoning_trace": [], "passage_estimate": None, "proposal": None}  # fmt: skip
    return {**base, **over}


def route(mode, **kw):
    return {"execution_mode": mode, "deterministic_intent": None, "answer_size": "standard", "standalone_question": "",
            "search_terms": [], "reason": "", **kw}  # fmt: skip


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
        emails=[ChatEmail(email_id="E046", subject="M/V VSL-02//ROB", sender="Master", excerpt=E046_TEXT)],
    )  # fmt: skip


def ask(question, llm, history=None, run_tool=None):
    req = ChatRequest(question=question, history=[ChatTurn(**h) for h in history or []])
    return v7.e16v7_answer_chat(req, context(), llm, NOW, run_tool)


# --- 4.1 structured output ------------------------------------------------------------------------


def _check_strict(schema: dict, path="") -> None:
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False, path
        assert sorted(schema["required"]) == sorted(schema["properties"]), path
        for k, sub in schema["properties"].items():
            _check_strict(sub, f"{path}.{k}")
    for sub in schema.get("anyOf", []):
        _check_strict(sub, path)
    if "items" in schema:
        _check_strict(schema["items"], path + "[]")


def test_schemas_follow_openai_strict_rules_and_match_the_models():
    _check_strict(v7.ANSWER_SCHEMA)
    _check_strict(v7.ROUTER_SCHEMA)
    assert set(v7.ANSWER_SCHEMA["properties"]) == set(v7.AnswerOut.model_fields)
    assert set(v7.ROUTER_SCHEMA["properties"]) == set(v7.RouterOut.model_fields)
    assert set(v7.ANSWER_SCHEMA["properties"]["evidence"]["items"]["properties"]) == set(v7.EvidenceOut.model_fields)
    assert set(v7.ANSWER_SCHEMA["properties"]["sources"]["items"]["properties"]) == set(v7.SourceOut.model_fields)


def test_schemas_are_registered_for_the_v7_nodes():
    from src import llm_client

    assert llm_client.STRICT_SCHEMAS["E16_V7"][1] is v7.ANSWER_SCHEMA
    assert llm_client.STRICT_SCHEMAS["E16_V7_ROUTER"][1] is v7.ROUTER_SCHEMA


def test_the_prompt_carries_the_evidence_rules_and_the_new_contract():
    assert "EVIDENCE" in v7.E16_SYSTEM_V7 and '"evidence": [{"claim"' in v7.E16_SYSTEM_V7
    assert v7.E16_SYSTEM_V7.count("OUTPUT CONTRACT") == 1


def test_router_enum_is_enforced_and_a_misplaced_intent_is_repaired():
    llm = FakeLlm(routes=route("open_tasks"))  # the v6 live finding: the intent in execution_mode
    assert "共 1 项" in ask("目前待办事项", llm).text
    bad = FakeLlm(routes=route("something else"))
    assert ask("目前待办事项", bad).llm_status == "failed"
    no_intent = FakeLlm(routes=route("deterministic"))  # deterministic without an intent is unusable
    assert ask("目前待办事项", no_intent).llm_status == "failed"


def test_an_invalid_answer_gets_one_repair_then_fails_closed():
    bad = full(evidence_status="mostly fine")
    good = full(answer="CPY-14（E046）。")
    llm = FakeLlm(routes=route("evidence_reasoning"), answers=[bad, good])
    assert ask("VSL-02在Newcastle港代理", llm).text.startswith("CPY-14")
    assert llm.calls[-1][1].endswith("-r")  # the repair call has its own recording key
    twice = FakeLlm(routes=route("evidence_reasoning"), answers=[bad, bad])
    assert ask("VSL-02在Newcastle港代理", twice).llm_status == "failed"


def test_a_draft_object_is_still_accepted_and_rendered_as_text():
    llm = FakeLlm(routes=route("evidence_reasoning"),
                  answers=[full(answer="草稿。", draft={"subject": "Hire due", "body": "Dear PER-33,"})])
    assert ask("起草一封邮件", llm).draft == "Subject: Hire due\n\nDear PER-33,"


# --- 4.2 evidence contract --------------------------------------------------------------------------


def test_quote_matching_ignores_whitespace_case_and_curly_quotes_and_honours_ellipsis():
    assert v7.quote_in_text("arrival  discharge\nport distance 1400NM", E046_TEXT)
    assert v7.quote_in_text("Please kindly find ... Distance 1400nm including 80nm ECA", E046_TEXT)
    assert not v7.quote_in_text("Distance 1450nm", E046_TEXT)
    assert not v7.quote_in_text("1400nm", E046_TEXT)  # too short to prove anything
    assert not v7.quote_in_text("Please kindly find ... Berth schedule confirmed", E046_TEXT)


def evidence(source, quote, claim="distance"):
    return {"claim": claim, "source_id": source, "quote": quote}


def test_a_verbatim_quote_is_verified_and_a_wrong_or_unread_one_is_flagged():
    answer = full(answer="航程约 1,400 nm（E046）。", sources=[{"kind": "email", "id": "E046", "label": ""}],
                  evidence=[evidence("E046", "Distance 1400nm including 80nm ECA"),
                            evidence("E046", "Distance 1500nm including 80nm ECA", "other distance"),
                            evidence("E099", "Vessel sailed at 14:48 LT on 30 July", "sailed")])  # fmt: skip
    result = ask("VSL-02 到 Newcastle 距离", FakeLlm(routes=route("evidence_reasoning"), answers=[answer]))
    assert [e.status for e in result.evidence] == ["verified", "quote_not_found", "source_not_read"]
    assert "other distance [E046]" in result.details and "sailed [E099]" in result.details
    assert "distance [E046]" not in result.details.replace("other distance [E046]", "")
    assert result.evidence_status == "partial"  # sufficient is downgraded
    assert any("1 of 3 quote(s) verified" in t or "2 of 3 quote(s) not verified" in t for t in result.reasoning_trace)


def test_all_quotes_verified_keeps_the_status():
    answer = full(answer="航程约 1,400 nm（E046）。", sources=[{"kind": "email", "id": "E046", "label": ""}],
                  evidence=[evidence("E046", "Distance 1400nm including 80nm ECA")])  # fmt: skip
    result = ask("VSL-02 到 Newcastle 距离", FakeLlm(routes=route("evidence_reasoning"), answers=[answer]))
    assert result.evidence[0].status == "verified" and result.evidence_status == "sufficient"
    assert any("1 of 1 quote(s) verified" in t for t in result.reasoning_trace)


def test_a_quote_from_a_full_email_read_through_the_tool_counts():
    full_email = {"email_id": "E063", "subject": "VSL-01 RELEASE CARGO", "vessel": "VSL-01",
                  "text": "Please be advised that the Charterer CPY-02 have sent their LOI", "quoted_thread": ""}  # fmt: skip
    answer = full(answer="CPY-02 提交了 LOI（E063）。", sources=[{"kind": "email", "id": "E063", "label": ""}],
                  evidence=[evidence("E063", "the Charterer CPY-02 have sent their LOI", "LOI sent")])  # fmt: skip
    llm = FakeLlm(routes=route("evidence_reasoning"),
                  turns=[{"tool_calls": [{"name": "get_email", "arguments": {"email_id": "E063"}}]}, {"final": answer}])  # fmt: skip
    result = ask("VSL-01 的 LOI", llm, run_tool=lambda name, args: full_email)
    assert result.evidence[0].status == "verified"


def test_citing_company_records_without_any_quote_is_flagged():
    answer = full(answer="CPY-14（E046）。", sources=[{"kind": "email", "id": "E046", "label": ""}])
    result = ask("VSL-02 在 Newcastle 的代理", FakeLlm(routes=route("evidence_reasoning"), answers=[answer]))
    assert "没有给出原文摘录" in result.details and result.evidence_status == "partial"


def test_domain_knowledge_without_company_sources_needs_no_quote():
    answer = full(answer="一般做法：确认泊位。", evidence_status="partial")
    result = ask("Newcastle港要注意什么", FakeLlm(routes=route("domain_knowledge"), answers=[answer]))
    assert result.details is None or "摘录" not in result.details


def test_a_vessel_code_nobody_gave_the_model_is_flagged():
    answer = full(answer="VSL-77 的 ROB 是 451.024 MT。")
    result = ask("VSL-02 的 ROB", FakeLlm(routes=route("evidence_reasoning"), answers=[answer]))
    assert "VSL-77" in result.details and "451.024" not in result.details


# --- 4.3 output scan --------------------------------------------------------------------------------


def test_scrub_hides_id_numbers_phones_and_addresses_but_not_ordinary_numbers():
    text = "ID 11010519900307123X, old 110105900307123, passport E12345678, call +86 138 0013 8000, Add: 1 Harbour Road"
    out, n = v7.scrub(text)
    assert n == 5 and out.count(v7.HIDDEN) == 5
    for leaked in ("11010519900307123X", "110105900307123", "E12345678", "138 0013 8000", "Harbour Road"):
        assert leaked not in out
    ordinary = "Cargo 61,520.00 WMT, ETA 2026-08-04 15:00, ROB 451.024 MT, mail01@CPY-01.example, PHONE-02, IMO 9412345"
    assert v7.scrub(ordinary) == (ordinary, 0)


def test_every_shown_part_of_an_answer_goes_through_the_scan():
    answer = full(answer="持证人 张三 11010519900307123X 将登轮（E046）。", details="号码 110105900307123",
                  draft="Subject: x\n\nID E12345678", sources=[{"kind": "email", "id": "E046", "label": ""}],
                  evidence=[evidence("E046", "Distance 1400nm including 80nm ECA")])  # fmt: skip
    result = ask("VSL-02 谁登轮", FakeLlm(routes=route("evidence_reasoning"), answers=[answer]))
    shown = " ".join([result.text, result.details or "", result.draft or ""])
    assert "11010519900307123X" not in shown and "110105900307123" not in shown and "E12345678" not in shown
    assert any(t.startswith("Output scan (code): 3 value(s) hidden") for t in result.reasoning_trace)


def test_deterministic_answers_also_leave_through_the_scan():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="vessel_facts"),
                  present={"summary": "ROB，联系 +86 138 0013 8000", "items": [{"label": "ROB", "value": "451.024 MT", "source": "E053"}]})  # fmt: skip
    result = ask("VSL-02 船存燃油", llm)
    assert "138 0013 8000" not in result.text and v7.HIDDEN in result.text


# --- unchanged v6 behaviour that v7 builds on --------------------------------------------------------


def test_follow_up_and_out_of_scope_still_work():
    prev = [{"role": "user", "text": "Newcastle港要注意什么"},
            {"role": "assistant", "text": "\n".join(["ETA 8/4（E053）"] + [f"- 通用建议 {i}" for i in range(12)])}]  # fmt: skip
    llm = FakeLlm(routes=route("follow_up", answer_size="short"), revise={"answer": "ETA 8/4（E053）。", "details": ""})
    assert ask("太长了", llm, history=prev).execution_mode == "follow_up"
    assert ask("我的猫可爱吗", FakeLlm(routes=route("out_of_scope", reason="这个我帮不上。"))).execution_mode == "out_of_scope"


def test_router_votes_and_all_calls_use_the_v7_nodes():
    llm = FakeLlm(routes=[route("out_of_scope"), route("deterministic", deterministic_intent="open_tasks"),
                          route("deterministic", deterministic_intent="open_tasks")])  # fmt: skip
    result = ask("目前待办事项", llm)
    assert result.reasoning_trace[0].startswith("Router: 2/3 samples agree on deterministic/open_tasks")
    assert {c[0] for c in llm.calls} == {"E16_V7_ROUTER"}


def test_pending_reply_stays_in_code():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="pending_reply"))
    answer = ask("哪些邮件待回复", llm)
    assert "当前没有" in answer.text and [c[0] for c in llm.calls] == ["E16_V7_ROUTER"] * 3


def test_a_router_failure_fails_closed():
    assert ask("目前待办事项", FakeLlm(routes=None)).llm_status == "failed"


# --- M1: hybrid retrieval behind the search tool ----------------------------------------------------

from src import e_nodes, retrieval  # noqa: E402
from src import playbooks as pbk  # noqa: E402
from src import verifier  # noqa: E402
from src.schemas import ParsedEmail, TimelineRow  # noqa: E402


def parsed(eid, subject, text, quoted=""):
    return ParsedEmail(email_id=eid, subject=subject, subject_norm=subject.lower(), sent_time=NOW, direction="Inbound",
                       sender="x@y", new_text=text, quoted_text=quoted)  # fmt: skip


class FakeStore:
    def __init__(self, emails, vessels):
        self.emails = {e.email_id: e for e in emails}
        self.vessels = vessels  # email_id -> vessel code

    def email_ids(self):
        return list(self.emails)

    def get_email(self, eid):
        return self.emails.get(eid)

    def proposal_rows(self, statuses):
        return [{"email_id": e, "proposal": SimpleNamespace(vessel=SimpleNamespace(vessel_code=v),
                                                           event=SimpleNamespace(event_type="Vessel Report"), statuses=["FYI - No Action"])}
                for e, v in self.vessels.items()]  # fmt: skip


CONCEPT_WORDS = [("berth", "anchorage", "码头", "锚地"), ("crane", "吊"), ("hire", "invoice", "租金")]


def concept_embed(texts):
    return [retrieval._normalise([10.0 if any(w in t.lower() for w in ws) else 0.0 for ws in CONCEPT_WORDS] + [0.01])  # noqa: SLF001
            for t in texts]


def backend_with(embedder, monkeypatch):
    monkeypatch.setattr(e_nodes, "chat_email_view", lambda email, kb: SimpleNamespace(sender="Master"))
    store = FakeStore([parsed("E046", "M/V VSL-02//ROB", "Stay in berth 2 days. Distance 1400nm."),
                       parsed("E049", "M/V VSL-02 DAILY", "Daily running hours of ship crane numbers: NO.1"),
                       parsed("E060", "MV VSL-01 30TH HIRE", "hire statement with bank confirmation")],
                      {"E046": "VSL-02", "E049": "VSL-02", "E060": "VSL-01"})  # fmt: skip
    return v7.RetrievalBackend(None, embedder), store


def test_search_with_text_is_hybrid_and_a_chinese_query_finds_the_english_email(monkeypatch):
    backend, store = backend_with(None, monkeypatch)
    assert backend.search({"text": "码头还是锚地"}, store, None) == []  # keyword only: nothing shared
    backend.embedder = lambda texts: concept_embed(texts)  # no index vectors, but also query only...
    backend._idx = None  # rebuild with vectors present
    chunks = [c for e in store.emails.values() for c in retrieval.email_chunks(e.email_id, e.subject, e.new_text, e.quoted_text)]
    backend._idx = retrieval.HybridIndex(chunks, {c.key: (c.sha, v) for c, v in zip(chunks, concept_embed([c.text for c in chunks]), strict=True)}, "fake")  # fmt: skip
    backend._ids = frozenset(store.email_ids())
    hits = backend.search({"text": "码头还是锚地"}, store, None)
    assert hits[0]["email_id"] == "E046" and "berth" in hits[0]["match"]
    assert set(hits[0]) >= {"email_id", "subject", "sent_time", "sender", "vessel", "event_type", "excerpt", "match"}


def test_search_filters_still_apply_and_an_embedding_failure_means_keywords_only(monkeypatch):
    def boom(_texts):
        raise RuntimeError("network")

    backend, store = backend_with(boom, monkeypatch)
    assert [h["email_id"] for h in backend.search({"text": "hire statement"}, store, None)] == ["E060"]
    assert backend.search({"text": "hire statement", "vessel": "VSL-02"}, store, None) == []
    assert [h["email_id"] for h in backend.search({"text": "crane", "vessel": "VSL-02"}, store, None)] == ["E049"]


def test_search_without_text_is_v5s_filter_and_the_index_is_rebuilt_when_emails_change(monkeypatch):
    backend, store = backend_with(None, monkeypatch)
    monkeypatch.setattr(v7.v5, "v5_search_emails", lambda args, st, kb: [{"email_id": "VIA-V5"}])
    assert backend.search({"vessel": "VSL-02"}, store, None) == [{"email_id": "VIA-V5"}]
    first = backend.index(store, None)
    assert backend.index(store, None) is first
    store.emails["E070"] = parsed("E070", "new", "anchorage notice")
    assert backend.index(store, None) is not first
    assert v7.run_tool_v7("search_emails", {"text": "anchorage notice"}, store, None, backend)[0]["email_id"] == "E070"
    with pytest.raises(ValueError):
        v7.run_tool_v7("delete_email", {}, store, None, backend)


# --- M2: verifier --------------------------------------------------------------------------------


def verdicts(*vs):
    """A verify() fake: the n-th claim (key suffix -vN) gets the n-th verdict."""
    return lambda key: {"verdict": vs[int(key.rsplit("-v", 1)[1])], "reason": f"reason {key[-2:]}"}


def l2_answer():
    return full(answer="E045 是租家的投诉。", sources=[{"kind": "email", "id": "E046", "label": ""}],
                evidence=[evidence("E046", "Distance 1400nm including 80nm ECA", "distance"),
                          evidence("E046", "Please kindly find the ROB calculation", "who pays")],
                proposal={"conclusion": "费用应由 Charterers 承担", "basis": [{"point": "距离", "source": "E046"}],
                          "counter_evidence": [], "missing_information": ["CP 条款"]})  # fmt: skip


def test_the_verifier_flags_claims_the_quote_does_not_support_and_weakens_an_l2_conclusion():
    llm = FakeLlm(routes=route("proposal_reasoning", answer_size="detailed"), answers=[l2_answer()],
                  verify=verdicts("supports", "insufficient"))  # fmt: skip
    result = ask("这笔费用Owners还是Charterers承担", llm)
    assert [e.support for e in result.evidence] == ["supports", "insufficient"]
    assert "（建议，证据不足，需复核）" in result.text and "⚠ 核验：1 条结论没有被所引原文支持" in result.text
    assert "who pays [E046]：reason v1" in result.details
    assert result.evidence_status == "missing_required_evidence"
    assert any("Verifier: 2 of 2 claim(s) checked, 1 not supported" in t for t in result.reasoning_trace)


def test_all_supported_claims_change_nothing_and_a_failed_verifier_never_blocks():
    ok = FakeLlm(routes=route("proposal_reasoning"), answers=[l2_answer()], verify=verdicts("supports", "supports"))
    result = ask("这笔费用Owners还是Charterers承担", ok)
    assert "⚠" not in result.text and "（建议，需复核）" in result.text and result.evidence_status == "sufficient"
    down = FakeLlm(routes=route("proposal_reasoning"), answers=[l2_answer()], verify=lambda key: (_ for _ in ()).throw(LlmError("x")))
    r2 = ask("这笔费用Owners还是Charterers承担", down)
    assert "⚠" not in r2.text and any("Verifier unavailable" in t for t in r2.reasoning_trace)


def test_the_verifier_runs_only_for_l2_detailed_or_high_stakes_questions():
    assert verifier.needs_verification("proposal_reasoning", "short", "x") and verifier.needs_verification("hybrid", "short", "x")
    assert verifier.needs_verification("evidence_reasoning", "detailed", "x")
    assert verifier.needs_verification("evidence_reasoning", "short", "VSL-01还有哪些待付发票")
    assert verifier.needs_verification("evidence_reasoning", "short", "核对B/L、MR和LOI")
    assert not verifier.needs_verification("evidence_reasoning", "short", "CPY-14 是谁")
    simple = FakeLlm(routes=route("evidence_reasoning", answer_size="short"),
                     answers=[full(answer="CPY-14（E046）。", sources=[{"kind": "email", "id": "E046", "label": ""}],
                                   evidence=[evidence("E046", "Distance 1400nm including 80nm ECA")])])  # fmt: skip
    ask("Newcastle 代理是谁", simple)
    assert "E16_V7_VERIFY" not in [c[0] for c in simple.calls]


def test_verdict_schema_matches_the_model_and_is_registered():
    from src import llm_client

    assert set(verifier.VERDICT_SCHEMA["properties"]) == set(verifier.VerdictOut.model_fields)
    _check_strict(verifier.VERDICT_SCHEMA)
    assert llm_client.STRICT_SCHEMAS[verifier.NODE][1] is verifier.VERDICT_SCHEMA


# --- M3: playbooks -----------------------------------------------------------------------------------

PB = pbk.parse_playbook("""---
id: hire-next-due
title: Next hire payment date
when: When the next hire payment is due.
mode: evidence_reasoning
status: approved
source: test
steps:
  - {id: s1, primitive: Select, text: "Find the latest hire statement."}
  - {id: s2, primitive: Transform, text: "Compute the next due date."}
---
Never assume an interval.
""")


def test_a_selected_playbook_is_in_the_prompt_and_its_steps_are_reported_and_checked():
    ans = full(answer="缺 CP 付款条款，无法算出下一期。", sources=[{"kind": "email", "id": "E046", "label": ""}],
               steps=[{"step_id": "s1", "status": "done", "note": "E046", "evidence_ids": ["E046"]},
                      {"step_id": "s2", "status": "done", "note": "guessed", "evidence_ids": ["E999"]}],
               evidence=[evidence("E046", "Distance 1400nm including 80nm ECA")])  # fmt: skip
    llm = FakeLlm(routes=route("evidence_reasoning", playbook="hire-next-due"), answers=[ans])
    req = ChatRequest(question="VSL-02 租金下一个due是哪天")
    result = v7.e16v7_answer_chat(req, context(), llm, NOW, playbooks={"hire-next-due": PB})
    assert "PLAYBOOK hire-next-due" in llm.systems["E16_V7"] and "Never assume an interval." in llm.systems["E16_V7"]
    assert "- hire-next-due: When the next hire payment is due." in llm.systems["E16_V7_ROUTER"]
    assert result.playbook.id == "hire-next-due"
    assert [(s.step_id, s.status) for s in result.steps] == [("s1", "done"), ("s2", "missing")]  # E999 was never read
    assert result.steps[0].primitive == "Select" and result.steps[0].text.startswith("Find the latest")
    assert any(t.startswith("Playbook hire-next-due: 1 of 2 step(s) done, 1 missing") for t in result.reasoning_trace)


def test_unknown_or_draft_playbooks_are_ignored_and_no_menu_means_plain_v6_behaviour(monkeypatch):
    monkeypatch.delenv("E16_INCLUDE_DRAFT_PLAYBOOKS", raising=False)
    draft = pbk.parse_playbook(PB.model_dump_json() and """---
id: draft-one
title: Draft
when: A draft question.
mode: hybrid
status: draft
source: test
steps:
  - {id: s1, primitive: Select, text: "x"}
---
""")
    llm = FakeLlm(routes=route("evidence_reasoning", playbook="draft-one"), answers=[full(answer="ok。")])
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-02 的 UWI"), context(), llm, NOW, playbooks={"draft-one": draft})
    assert result.playbook is None and result.steps == [] and "PLAYBOOKS" not in llm.systems["E16_V7_ROUTER"]
    monkeypatch.setenv("E16_INCLUDE_DRAFT_PLAYBOOKS", "1")
    llm2 = FakeLlm(routes=route("evidence_reasoning", playbook="draft-one"), answers=[full(answer="ok。")])
    r2 = v7.e16v7_answer_chat(ChatRequest(question="VSL-02 的 UWI"), context(), llm2, NOW, playbooks={"draft-one": draft})
    assert r2.playbook.status == "draft" and "(draft)" in llm2.systems["E16_V7"]
    bogus = FakeLlm(routes=route("evidence_reasoning", playbook="nope"), answers=[full(answer="ok。")])
    assert v7.e16v7_answer_chat(ChatRequest(question="x VSL-02"), context(), bogus, NOW, playbooks={"draft-one": draft}).playbook is None


def test_the_router_playbook_vote_is_a_majority_among_agreeing_samples():
    routes = [route("evidence_reasoning", playbook="hire-next-due"), route("evidence_reasoning", playbook="hire-next-due"),
              route("evidence_reasoning", playbook=None)]  # fmt: skip
    llm = FakeLlm(routes=routes, answers=[full(answer="ok。")])
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-02 租金下一个due"), context(), llm, NOW, playbooks={"hire-next-due": PB})
    assert result.playbook.id == "hire-next-due"


# --- M3: vessel facts from the reports --------------------------------------------------------------

REPORTS = {
    "E021": ("M/V VSL-02//Noon Report 20260724", "Dd: 24 Jul 2026\n(3) Daily GPS speed/Log speed:  14.2/13.0\n(8) Weather condition:SE/5  CLOUDY\n(9) Sea/Swell condition: 2M\n(11) Draft F/A:4.50/6.50"),
    "E024": ("M/V VSL-02// ARRIVAL REPORT 20260725", "Dd: 25 Jul 2026\n3.AVG SPD: 13.2KTS\n8. Remarks:Vessel encounter adverse strong current about 2.5 kn"),
}


def report_context():
    ctx = context()
    view = ctx.vessels[0].model_copy(update={"timeline": [
        TimelineRow(event_time=NOW, event_type="Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)", email_id=e) for e in REPORTS]})  # fmt: skip
    return ctx.model_copy(update={"vessels": [view]})


def report_tool(name, args):
    subject, text = REPORTS[args["email_id"]]
    return {"email_id": args["email_id"], "subject": subject, "sent_time": "2026-07-24T12:30:27+08:00", "text": text}


def test_a_weather_and_speed_question_is_answered_from_the_reports_in_code_without_a_model():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="vessel_facts"))
    req = ChatRequest(question="VSL-02这几天的速度和天气，有没有逆流")
    result = v7.e16v7_answer_chat(req, report_context(), llm, NOW, run_tool=report_tool)
    assert [c[0] for c in llm.calls] == ["E16_V7_ROUTER"] * 3  # no PRESENT call
    assert "- 7/24 午报（E021）：航速 GPS 14.2 / Log 13.0 kn；风 SE 5 级；海浪/涌 2 m；天气 Cloudy" in result.text
    assert "海流：Vessel encounter adverse strong current about 2.5 kn" in result.text
    assert {s.id for s in result.sources} == {"E021", "E024"} and result.evidence_status == "sufficient"


def test_a_draft_not_in_the_facts_comes_from_the_nearest_report_with_its_date_and_missing_is_said():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="vessel_facts"))
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-02 的吃水和油耗"), report_context(), llm, NOW, run_tool=report_tool)
    assert "- 7/24 午报（E021）：吃水 F 4.50 / A 6.50 m" in result.text
    assert "- 油耗：当前记录中没有找到" in result.text and result.evidence_status == "partial"


def test_a_question_that_also_asks_eta_or_rob_goes_to_the_model_with_the_digests():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="vessel_facts"),
                  present={"summary": "VSL-02：", "items": [{"label": "吃水（7/24 午报）", "value": "F 4.50 / A 6.50 m", "time": "7/24", "source": "E021"},
                                                          {"label": "ROB VLSFO", "value": "451.024 MT", "time": "7/30", "source": "E053"}],
                           "missing": []})  # fmt: skip
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-02 什么时候到港，存油多少，吃水多少"), report_context(), llm, NOW, run_tool=report_tool)
    digests = llm.users["E16_V7_PRESENT"]["context"]["report_digests"]
    assert digests[0]["email_id"] == "E021" and digests[0]["draft"] == "F 4.50 / A 6.50 m"
    assert "- 吃水（7/24 午报）：F 4.50 / A 6.50 m（7/24） [E021]" in result.text
    assert "451.024" in result.text  # E053's fact is in the fact store


def test_a_playbook_turns_a_deterministic_route_into_reasoning():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="dues", playbook="hire-next-due"),
                  answers=[full(answer="缺 CP 付款条款。")])
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-01 租金下一期什么时候到期"), context(), llm, NOW, playbooks={"hire-next-due": PB})
    assert result.execution_mode == "evidence_reasoning" and result.playbook.id == "hire-next-due"
    assert any("Playbook mode (code): deterministic -> evidence_reasoning" in t for t in result.reasoning_trace)


def test_no_vectors_in_the_index_means_no_embedding_call(monkeypatch):
    calls = []
    backend, store = backend_with(lambda texts: calls.append(texts) or concept_embed(texts), monkeypatch)
    assert backend.search({"text": "hire statement"}, store, None)[0]["email_id"] == "E060"
    assert calls == []


def test_a_playbook_sets_its_own_mode_whatever_the_router_said():
    cost = pbk.parse_playbook(PB.model_dump_json() and """---
id: cost-allocation
title: Who bears a cost
when: Which party bears a cost.
mode: proposal_reasoning
status: approved
source: test
steps:
  - {id: s1, primitive: Detect, text: "Identify the cost."}
---
""")
    ans = full(answer="缺具体费用。", proposal={"conclusion": "", "basis": [], "counter_evidence": [], "missing_information": ["费用名称"]})
    llm = FakeLlm(routes=route("evidence_reasoning", playbook="cost-allocation"), answers=[ans])
    result = v7.e16v7_answer_chat(ChatRequest(question="这笔费用 Owners 还是 Charterers 承担 VSL-02"), context(), llm, NOW,
                                  playbooks={"cost-allocation": cost})  # fmt: skip
    assert result.execution_mode == "proposal_reasoning" and result.capability_authority == "supported_l2"
    assert "（建议，需复核）" in result.text and any("Playbook mode (code): evidence_reasoning -> proposal_reasoning" in t for t in result.reasoning_trace)


def test_open_tasks_needs_task_wording_and_a_port_question_is_not_a_task_list():
    llm = FakeLlm(routes=route("deterministic", deterministic_intent="open_tasks"), answers=[full(answer="一般注意事项。", evidence_status="partial")])
    result = ask("Newcastle港要注意什么问题", llm)
    assert result.execution_mode == "domain_knowledge" and any("open_tasks overridden" in t for t in result.reasoning_trace)
    assert "共 1 项" in ask("今天还有哪些代办？", FakeLlm(routes=route("deterministic", deterministic_intent="open_tasks"))).text
    assert "Open tasks: 1." in ask("What needs my attention today?", FakeLlm(routes=route("deterministic", deterministic_intent="open_tasks"))).text


def test_a_report_field_question_the_router_called_out_of_scope_is_answered_from_the_reports():
    llm = FakeLlm(routes=route("out_of_scope", reason="不涉及航运"))
    result = v7.e16v7_answer_chat(ChatRequest(question="VSL-02这几天的风浪和海流"), report_context(), llm, NOW, run_tool=report_tool)
    assert result.execution_mode == "deterministic" and "午报（E021）" in result.text
    assert [c[0] for c in llm.calls] == ["E16_V7_ROUTER"] * 3
    analysing = FakeLlm(routes=route("evidence_reasoning"), turns=[{"final": full(answer="需要看索赔文件。")}])  # with a run_tool the answer comes through the tool loop
    r2 = v7.e16v7_answer_chat(ChatRequest(question="分析VSL-02这份油耗索赔是否合理"), report_context(), analysing, NOW, run_tool=report_tool)
    assert r2.execution_mode == "evidence_reasoning"  # an analysis is not a field lookup


def test_the_router_prompt_corrects_open_tasks_and_names_wind_sea_and_current():
    system = v7.E16_ROUTER_SYSTEM_V7
    assert "NOT \"what to watch out for\"" in system and "wind, sea state, current" in system


# --- v7.1 (docs/design_agent_e16_v7_1.md) -----------------------------------------------------------


def test_the_verifier_is_told_the_questions_language_and_a_short_quote_without_the_claims_number_is_not_sent():
    llm = FakeLlm(routes=route("proposal_reasoning", answer_size="detailed"), answers=[l2_answer()], verify=verdicts("supports", "supports"))
    ask("这笔费用Owners还是Charterers承担", llm)
    assert llm.users["E16_V7_VERIFY"]["language"] == "zh"
    assert verifier.weak_quote("Distance 1400 nm", "Distance")
    assert not verifier.weak_quote("Distance 1400 nm", "Distance 1400nm including 80nm ECA")
    assert not verifier.weak_quote("the berth is Dampier", "Dampier")  # no number in the claim: nothing to lack
    assert "language" in verifier.VERIFY_SYSTEM


def test_email_ids_are_no_longer_listed_as_a_sources_line_in_the_text():
    llm = FakeLlm(routes=route("proposal_reasoning"), answers=[l2_answer()], verify=verdicts("supports", "supports"))
    result = ask("这笔费用Owners还是Charterers承担", llm)
    assert "来源：" not in result.text and [s.id for s in result.sources] == ["E046"]


# --- reference distances (docs/design_agent_e16_v7_1.md 11) --------------------------------------------------------
from src import distances  # noqa: E402


def test_a_tabled_port_pair_at_a_stated_speed_is_answered_in_code_with_its_source_and_no_model_call():
    llm = FakeLlm(routes=None)  # a router call would raise
    result = ask("从天津到新加坡，航速 12 节要几天？", llm)
    assert llm.calls == []
    assert result.text.startswith("天津 → 新加坡") and "2,768" in result.text and "230.7 小时" in result.text and "9.6 天" in result.text
    assert "11 节 10.5 天" in result.text and "13 节 8.9 天" in result.text and "NetPAS" in result.text
    assert result.execution_mode == "deterministic" and "kb/distances.csv" in result.details


def test_the_pair_in_english_or_with_either_order_matches_but_a_missing_speed_or_pair_does_not():
    assert distances.find("How many days Singapore to Tianjin at 12 knots?") is not None
    assert distances.find("天津到新加坡要几天") is None  # no speed
    assert distances.find("从天津到青岛，12 节要几天？") is None  # not in the table
    text, _ = distances.render(distances.DEFAULT[0], 12.0, zh=False)
    assert "9.6 days" in text and "Source: distance reference table" in text


# --- dues in code, and "draft" the verb (docs/design_agent_e16_v7_1.md 12) ------------------------------------------------


def context_with_dues(rows):
    ctx = context()
    return ctx.model_copy(update={"dues": DueList(items=rows, store_status="ok")})


def test_dues_are_written_in_code_in_the_questions_language_with_upcoming_first_and_overdue_noted():
    from datetime import date

    from src.schemas import DueRow

    def row(tid, vessel, due, kind="Hire", overdue=False):
        return DueRow(task_id=tid, action_id=tid + "-a", vessel=vessel, action=f"Verify the payment for {vessel}, due on {due}.", due_type=kind,
                      due_date=date.fromisoformat(due), priority=3, overdue=overdue)

    ctx = context_with_dues([row("T1", "VSL-01", "2026-10-16"), row("T2", "VSL-02", "2026-10-16"), row("T3", "VSL-03", "2026-10-01", overdue=True),
                             row("T4", "VSL-04", "2026-11-19", kind="Others")])
    en = v7.dues_rendered("Which dues are in the next 7 days?", ctx, False, "2026-10-12")
    assert en.text.startswith("Dues in the next 7 days: 2, plus 1 overdue") and "- 16 Oct · VSL-01 · Hire: Verify the payment for VSL-01" in en.text
    assert "Overdue: VSL-03 1 Oct" in en.text and "VSL-04" not in en.text and [s.id for s in en.sources] == ["T1", "T2"]
    zh = v7.dues_rendered("未来 30 天有哪些到期？", ctx, True, "2026-10-12")
    assert zh.text.startswith("未来 30 天内到期共 2 项，另有 1 项已逾期") and "- 10/16 · VSL-01" in zh.text
    assert v7.dues_rendered("dues?", context_with_dues([]), False, "2026-10-12") is None


def test_draft_the_verb_is_not_a_report_field_but_the_vessel_draft_still_is():
    from src import report_digest as rd

    assert rd.wanted_fields("Draft a reply to the Chittagong notice for VSL-07") == set()
    assert rd.wanted_fields("Draft an email to the agent") == set()
    assert rd.wanted_fields("What is the draft of VSL-13 now?") == {"draft"} and rd.wanted_fields("VSL-13 现在吃水多少") == {"draft"}
