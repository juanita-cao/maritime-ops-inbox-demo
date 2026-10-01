"""Golden questions for the mock dataset (docs/design_mock_data.md 6): one per scenario ground truth, plus report-field
and no-data cases. The expected facts are the numbers and words the ledger fixes, so a wrong answer cannot pass.
Checks use the same vocabulary as eval/golden_e16.json (docs/design_agent_e16_v6.md 3).

  python -m mockdata.golden      writes datasets/mock/eval/golden_e16.json"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("S01", "VSL-11 能不能在这个航次内安排水下检查或清洗？", {"playbook": "uwi-uwc-arrangement", "contains_any": [["Rizhao", "日照"], ["锚地", "3,800", "3800", "不适合", "无法", "不能"]], "max_lines": 12}),
    ("S02", "核对 VSL-11 在 Kamsar 装的铝矾土的 B/L、大副收据和 LOI，数量一致吗？", {"playbook": "document-crosscheck", "contains_any": [["78,420", "78420"], ["78,050", "78050", "370"]], "not_contains": ["三者信息一致", "信息是一致的"], "max_lines": 12}),
    ("S03", "VSL-12 在北海 ECA 烧的低硫油费用应该谁承担？", {"contains_any": [["clause 12", "第12条", "第 12 条", "条款"], ["复核", "review"]], "not_contains": ["应由Owners承担。"], "max_lines": 12}),
    ("S04", "VSL-12 的租金下一次什么时候到期？有没有被扣？", {"playbook": "hire-next-due", "contains_any": [["16 Oct", "10月16", "10/16", "2026-10-16"], ["11.5", "7.5", "4.0"]], "max_lines": 12}),
    ("S05", "VSL-12 的还船通知和还船油量怎么安排？", {"contains_any": [["Casablanca", "卡萨布兰卡"], ["598", "318", "905"]], "max_lines": 12}),
    ("S06", "VSL-13 在 Richards Bay 的最终 DA 是多少？哪些费用有争议？", {"contains_any": [["31,780", "31780"], ["31,870", "31870", "pre-loading", "装前", "理货", "tally"]], "max_lines": 12}),
    ("S07", "VSL-13 货舱进水的索赔现在什么情况？", {"contains_any": [["hold no.4", "4舱", "第4舱", "4 舱", "no.4"], ["2,950", "2950", "14 Oct", "10月14", "10/14"]], "max_lines": 12}),
    ("S08", "VSL-14 租家的航速油耗索赔成立吗？", {"contains_any": [["good weather", "良好天气", "12.5", "12.45"], ["21,500", "21500"]], "max_lines": 12}),
    ("S09", "VSL-15 的滞期费双方各自怎么算？", {"contains_any": [["12,950", "12950"], ["8,866", "8866"]], "max_lines": 12}),
    ("S10", "VSL-16 清舱重验耽误的时间谁承担？", {"contains_any": [["33.5"], ["clause 28", "第28条", "第 28 条", "条款"]], "max_lines": 12}),
    ("S11", "VSL-11 主机停车的停租怎么算？", {"contains_any": [["6.0", "6 小时", "6小时"], ["3.5", "12.0", "航速"]], "max_lines": 12}),
    ("S12", "VSL-20 在青岛 PSC 滞留是怎么回事？", {"contains_any": [["40.8"], ["3 项", "三项", "3项", "deficienc", "缺陷"]], "max_lines": 12}),
    ("S13", "VSL-12 在鹿特丹加的油硫含量超标吗？", {"contains_any": [["0.54"], ["0.05", "容差", "tolerance"]], "max_lines": 12}),
    ("S14", "VSL-17 在 Chittagong 要等多久，谁的时间？", {"contains_any": [["19 Oct", "10月19", "10/19"], ["租家", "charterer", "Charterer"]], "max_lines": 12}),
    ("S15", "VSL-18 的医疗送医情况和费用谁出？", {"contains_any": [["6.5"], ["Benoa"]], "max_lines": 12}),
    ("S16", "VSL-19 能不能同意转租给 Altai Trade FZE？", {"contains_any": [["不能", "暂不", "尚未", "not yet", "不同意", "不建议"], ["84", "股权", "ownership", "所有权"]], "max_lines": 12}),
    ("S17", "VSL-11 下一个航次 Newcastle 煤炭的成交条件是什么？", {"contains_any": [["18.6"], ["19,500", "19500"]], "max_lines": 12}),
    ("S18", "VSL-13 在 Mundra 的货差索赔是什么情况？", {"contains_any": [["410"], ["0.5", "41,000", "41000"]], "max_lines": 12}),
    ("W1-weather", "VSL-12 这几天的风浪", {"mode": ["deterministic"], "contains": ["午报"], "max_lines": 9}),
    ("D1-draft", "VSL-13 现在吃水多少", {"mode": ["deterministic"], "contains": ["吃水 F 12.55 / A 12.95"], "max_lines": 4}),
    ("P5-port-arrival", "Paradip 港要注意什么问题", {"playbook": "port-arrival-checklist", "steps_min": 3, "max_lines": 12}),
    ("D3-passage", "从天津到新加坡，航速 12 节要几天？", {"contains_any": [["天"], ["一般", "通用", "估算", "约", "大约"], ["海里", "nm"]], "max_lines": 8}),
    ("N1-no-data", "VSL-14 的船员名单是什么", {"contains_any": [["没有", "未找到", "无法", "not found", "no "]], "max_lines": 6}),
]


def main() -> None:
    out = ROOT / "datasets" / "mock" / "eval"
    out.mkdir(parents=True, exist_ok=True)
    cases = [{"id": cid, "question": q, "note": "ground truth in datasets/mock/truths.json" if cid.startswith("S") else "", "checks": checks} for cid, q, checks in CASES]
    (out / "golden_e16.json").write_text(json.dumps({"about": "Mock dataset golden questions (mockdata/golden.py); expected facts come from the ledger.", "cases": cases}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(cases), "cases written")


if __name__ == "__main__":
    main()
