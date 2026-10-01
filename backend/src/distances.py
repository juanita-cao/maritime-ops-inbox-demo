"""Reference port-to-port distances (docs/design_agent_e16_v7_1.md 11). A passage-time question that names two
ports of the table and a speed is answered in code from the table: the distance comes from a routing lookup
the owner made (not from a model's memory), the arithmetic is code, and the answer says where the number is from.
The table is a plain file, kb/distances.csv, shared by both datasets; a pair that is not in it still goes to the
model as a general estimate, labelled as one."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from src.settings import REPO_ROOT

_SPEED = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:节|kn\b|kts?\b|knots?\b)", re.I)
_PASSAGE = re.compile(r"几天|多少天|多久|需要多长|航行时间|航程|days?\b|how long|passage|steaming", re.I)


@dataclass(frozen=True)
class Distance:
    port_a: str
    port_b: str
    nm: float
    names_a: tuple[str, ...]
    names_b: tuple[str, ...]
    source: str
    as_of: str
    note: str


def load(path: Path) -> list[Distance]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            names = lambda key, port: tuple(x.strip().lower() for x in [port, *r[key].split(";")] if x.strip())  # noqa: E731
            out.append(Distance(r["port_a"], r["port_b"], float(r["distance_nm"]), names(
                "aliases_a", r["port_a"]), names("aliases_b", r["port_b"]), r["source"], r["as_of"], r.get("note", "")))
    return out


DEFAULT = load(REPO_ROOT / "kb" / "distances.csv")


def _mentions(question: str, names: tuple[str, ...]) -> int:
    """Where the first name occurs in the question, or -1."""
    low = question.lower()
    at = [low.find(n) for n in names if low.find(n) >= 0]
    return min(at) if at else -1


def find(question: str, table: list[Distance] | None = None) -> tuple[Distance, float] | None:
    """(the table row, the speed in knots) when the question asks for a passage time between two tabled ports at a stated speed."""
    m = _SPEED.search(question)
    if not m or not _PASSAGE.search(question):
        return None
    for row in DEFAULT if table is None else table:
        if _mentions(question, row.names_a) >= 0 and _mentions(question, row.names_b) >= 0:
            return row, float(m.group(1))
    return None


def render(row: Distance, knots: float, zh: bool) -> tuple[str, str]:
    """(the answer, the basis) for a passage at `knots`; neighbouring speeds are shown for comparison."""
    hours = row.nm / knots
    days = hours / 24
    others = [k for k in (knots - 1, knots + 1) if k > 0]
    near = "、".join(f"{k:g} 节 {row.nm / k / 24:.1f} 天" for k in others) if zh else ", ".join(f"{k:g} kn {row.nm / k / 24:.1f} days" for k in others)
    if zh:
        a, b = (next((n for n in names if re.search(r"[一-鿿]", n)), port) for names, port in ((row.names_a, row.port_a), (row.names_b, row.port_b)))
        text = (f"{a} → {b}：约 **{row.nm:,.0f} 海里**（{row.source}，{row.as_of} 查询）。\n"
                f"{knots:g} 节：{row.nm:,.0f} ÷ {knots:g} = {hours:.1f} 小时，约 **{days:.1f} 天**纯航行。\n"
                f"对比：{near}。\n"
                "未含港口停时、天气、绕航和减速区；实际计划以 routing 工具为准。\n"
                "来源：距离参考表（非公司邮件记录）")
        basis = f"距离取自参考表 kb/distances.csv：{a}–{b} {row.nm:,.0f} nm，{row.source}，{row.as_of}。时间 = 距离 ÷ 航速，由代码计算，不是模型估算。" + (f" {row.note}" if row.note else "")
        return text, basis
    text = (f"{row.port_a} → {row.port_b}: about **{row.nm:,.0f} nm** ({row.source}, looked up {row.as_of}).\n"
            f"At {knots:g} kn: {row.nm:,.0f} ÷ {knots:g} = {hours:.1f} hours, about **{days:.1f} days** steaming.\n"
            f"For comparison: {near}.\n"
            "Excludes port time, weather, deviations and slow-steaming zones; use a routing tool for planning.\n"
            "Source: distance reference table (not a company email record)")
    basis = f"Distance from the reference table kb/distances.csv: {row.port_a}–{row.port_b} {row.nm:,.0f} nm, {row.source}, {row.as_of}. Time = distance ÷ speed, computed in code, not estimated by a model." + (f" {row.note}" if row.note else "")
    return text, basis
