"""Field rules for vessel reports (docs/design_agent_e16_v7.md 7.5), in code.

The masters' noon, arrival, departure and daily reports come in a few fixed layouts. Reading wind
force, sea state, current, speed, consumption and draft out of them is pattern work, so it is done
here, not by a model: a question about weather or speed is answered from these rows, and a draft
that is not in the current facts is taken from the nearest report that states one, with its date.
"""

import re
from dataclasses import dataclass, field

_F = r"([\d]+(?:\.\d+)?)"


@dataclass
class ReportDigest:
    email_id: str
    when: str  # ISO date
    kind: str  # noon | arrival | departure | daily | eta | other
    speed_day: str | None = None  # "GPS 14.2 / Log 13.0 kn"
    speed_avg: str | None = None
    consumption: str | None = None  # "VLSFO 25.530 mt, LSMGO 0 mt"
    wind: str | None = None  # "SE force 5"
    sea: str | None = None  # "2 m"
    sky: str | None = None  # "Cloudy"
    current: str | None = None  # the master's remark about current
    draft: str | None = None  # "F 4.50 / A 6.50 m"
    draft_label: str | None = None  # "report" | "sailing" | "estimated arrival"
    rob: str | None = None
    fields: set[str] = field(default_factory=set)

    def has(self, wanted: set[str]) -> bool:
        return bool(self.fields & wanted)


def _kind(subject: str, text: str) -> str:
    s = subject.lower()
    for key, kind in (("noon", "noon"), ("arrival report", "arrival"), ("cosp", "departure"), ("departure", "departure"),
                      ("sailing report", "departure"), ("daily eta", "eta"), ("eta notice", "eta"), ("daily report", "daily")):  # fmt: skip
        if key in s:
            return kind
    return "other"


def _date(sent_iso: str, text: str) -> str:
    m = re.search(r"Dd:\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", text)
    if m:
        months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
        mon = months.index(m.group(2).lower()) + 1 if m.group(2).lower() in months else 0
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return sent_iso[:10]


def digest_email(email_id: str, subject: str, sent_iso: str, text: str) -> ReportDigest:
    d = ReportDigest(email_id=email_id, when=_date(sent_iso, text), kind=_kind(subject, text))
    flat = text.replace("\r", "")

    m = re.search(rf"Daily GPS speed\s*/\s*Log speed:\s*{_F}\s*/\s*{_F}", flat, re.I)
    if m:
        d.speed_day = f"GPS {m.group(1)} / Log {m.group(2)} kn"
    m = re.search(rf"Average GPS speed\s*/\s*Log Speed:\s*{_F}\s*/\s*{_F}", flat, re.I)
    if m:
        d.speed_avg = f"GPS {m.group(1)} / Log {m.group(2)} kn"
    if not (d.speed_day or d.speed_avg):
        m = re.search(rf"Course/avg spd/rpm/eng slip:\s*[\d.]+\s*/\s*{_F}\s*/", flat, re.I) or re.search(rf"AVG SPD:\s*{_F}\s*KTS", flat, re.I)
        if m:
            d.speed_avg = f"{m.group(1)} kn"

    m = re.search(rf"IFO Consumed/LSMGO consumed fm last report:\s*VLSFO\s*{_F}\s*mt\s*LSMGO\s*{_F}", flat, re.I)
    if m:
        d.consumption = f"VLSFO {m.group(1)} mt, LSMGO {m.group(2)} mt"
    if not d.consumption:
        m = re.search(rf"Avg daily consumption of fuel/diesel/water:\s*{_F}\s*/\s*{_F}\s*/\s*{_F}", flat, re.I)
        if m:
            d.consumption = f"VLSFO {m.group(1)} mt, LSMGO {m.group(2)} mt"
    if not d.consumption:
        m = re.search(rf"DAILY FO CONSUMPTION:\s*{_F}\s*MT", flat, re.I)
        if m:
            d.consumption = f"VLSFO {m.group(1)} mt"
    if not d.consumption:
        m = re.search(rf"Bunker consumed in past [\d.]+ hrs[^-\n]*---\s*VLSFO\s*{_F}\s*mt\s*/\s*LSMGO\s*{_F}", flat, re.I)
        if m:
            d.consumption = f"VLSFO {m.group(1)} mt, LSMGO {m.group(2)} mt"

    m = re.search(r"Weather condition:\s*([A-Z]{1,3})\s*/\s*(\d+)\s+([A-Za-z ]+)", flat)
    if m:
        d.wind, d.sky = f"{m.group(1)} force {m.group(2)}", m.group(3).strip().title()
    m = re.search(r"Wind direction/force/sea cond/vis:\s*([A-Z]{1,3})\s*/\s*(\d+)\s*/\s*([\d.]+\s*M)\s*/\s*(\w+)", flat, re.I)
    if m:
        d.wind, d.sea = f"{m.group(1).upper()} force {m.group(2)}", m.group(3).replace(" ", "").lower().replace("m", " m").strip()
    m = re.search(rf"Sea/Swell condition:\s*{_F}\s*M", flat, re.I)
    if m:
        d.sea = f"{m.group(1)} m"
    if not d.sky:
        m = re.search(r"WEATHER CONDITIONS? (?:PRESENT)?\s*[:\-]+\s*([A-Za-z ]+)|Weather condition-{2,}\s*([A-Za-z ]+)", flat, re.I)
        if m:
            d.sky = (m.group(1) or m.group(2)).strip().title()

    for line in re.split(r"\n|\.(?!\d)", flat):  # a full stop, not the point in "2.5"
        if re.search(r"\bcurrent\b", line, re.I) and re.search(r"adverse|favou?rable|strong|\bkn\b|knot", line, re.I):
            d.current = " ".join(line.replace("Remarks:", "").replace("Remark:", "").split())
            break

    for pattern, label in ((rf"Draft F/A:\s*{_F}\s*/\s*{_F}", "report"), (rf"Sailing Draft:\s*F\s*{_F}\s*m?\s*/\s*A\s*{_F}", "sailing"),
                           (rf"Departure Draft\s*:\s*F\s*{_F}\s*M?\s*/\s*A\s*{_F}", "sailing"),
                           (rf"Est Arr Draft:\s*FWD\s*/?\s*{_F}\s*m\s*AFT\s*/?\s*{_F}", "estimated arrival")):  # fmt: skip
        m = re.search(pattern, flat, re.I)
        if m:
            d.draft, d.draft_label = f"F {m.group(1)} / A {m.group(2)} m", label
            break

    m = re.search(r"ROB[^:\n]*:\s*(VLSFO[^\n]*|[\d.]+\s*MT/[^\n]*)", flat, re.I)
    if m:
        d.rob = m.group(1).strip()

    for name, value in (("speed", d.speed_day or d.speed_avg), ("consumption", d.consumption), ("weather", d.wind or d.sea or d.sky or d.current),
                        ("draft", d.draft)):  # fmt: skip
        if value:
            d.fields.add(name)
    return d


# --- which fields a question wants ---------------------------------------------------------------

_WANT = {
    "weather": re.compile(r"天气|风|浪|涌|海况|逆流|顺流|海流|流速|weather|wind|\bsea\b|swell|current", re.I),
    "speed": re.compile(r"速度|航速|\bspeed\b", re.I),
    "consumption": re.compile(r"油耗|耗油|消耗|consumption", re.I),
    "draft": re.compile(r"吃水|draft", re.I),
}
_BASE = re.compile(r"到港|到达|ETA|ETB|ETD|靠泊|开航|离港|燃油|淡水|存油|存量|ROB|货|装了|卸了|位置|在哪|cargo|fresh water|bunker|arrive", re.I)


def wanted_fields(question: str) -> set[str]:
    return {k for k, rx in _WANT.items() if rx.search(question)}


def needs_base_facts(question: str) -> bool:
    """The question also asks for current facts (ETA, ROB, cargo ...), which come from the fact store."""
    return bool(_BASE.search(question))


# --- selection and rendering -----------------------------------------------------------------------

MAX_ROWS = 5


def select(digests: list[ReportDigest], wanted: set[str]) -> list[ReportDigest]:
    """Newest first, field by field, so a field that only the older reports carry is not crowded out
    by newer reports that carry another one (the in-port daily reports have consumption and sky but
    no speed). One field: its MAX_ROWS newest reports; several: 2 each. Weather uses the reports
    with wind, sea state or a current remark (the noon and arrival reports of the leg) plus the
    newest sky-only report when it is newer; a draft is the one newest report that states one."""
    ordered = sorted(digests, key=lambda d: (d.when, d.email_id), reverse=True)
    picked: list[ReportDigest] = []

    def add(items: list[ReportDigest]) -> None:
        picked.extend(d for d in items if d not in picked)

    if "draft" in wanted:
        add([d for d in ordered if d.draft][:1])
    rest = wanted - {"draft"}
    per = MAX_ROWS if len(rest) <= 1 else 2
    rich: list[ReportDigest] = []
    for f in sorted(rest):
        if f == "weather":
            rich = [d for d in ordered if d.wind or d.sea or d.current]
            add(rich[:per])
        elif f == "speed":
            add([d for d in ordered if d.speed_day or d.speed_avg][:per])
        elif f == "consumption":
            add([d for d in ordered if d.consumption][:per])
    if "weather" in rest:
        sky = next((d for d in ordered if d.sky), None)
        if sky and sky not in picked and (not rich or (sky.when, sky.email_id) > (rich[0].when, rich[0].email_id)):
            picked.append(sky)
    return sorted(picked, key=lambda d: (d.when, d.email_id), reverse=True)


def _md(iso: str) -> str:
    return f"{int(iso[5:7])}/{int(iso[8:10])}"


def render_row(d: ReportDigest, wanted: set[str], zh: bool) -> str:
    kind = {"noon": ("午报", "noon"), "arrival": ("抵港报", "arrival"), "departure": ("离港报", "departure"),
            "daily": ("日报", "daily"), "eta": ("ETA 通知", "ETA notice")}.get(d.kind, ("报告", "report"))
    parts: list[str] = []
    if "speed" in wanted and (d.speed_day or d.speed_avg):
        parts.append((f"航速 {d.speed_day}" if d.speed_day else f"平均航速 {d.speed_avg}") if zh else (f"speed {d.speed_day}" if d.speed_day else f"avg speed {d.speed_avg}"))
    if "consumption" in wanted and d.consumption:
        parts.append(f"油耗 {d.consumption}" if zh else f"consumption {d.consumption}")
    if "weather" in wanted:
        if d.wind:
            parts.append("风 " + re.sub(r"force (\d+)", r"\1 级", d.wind) if zh else f"wind {d.wind}")
        if d.sea:
            parts.append(f"海浪/涌 {d.sea}" if zh else f"sea/swell {d.sea}")
        if d.sky:
            parts.append(f"天气 {d.sky}" if zh else f"weather {d.sky}")
        if d.current:
            parts.append(f"海流：{d.current}" if zh else f"current: {d.current}")
    if "draft" in wanted and d.draft:
        label = {"report": "", "sailing": "（开航吃水）", "estimated arrival": "（预计到港吃水）"}[d.draft_label or "report"]
        parts.append(f"吃水 {d.draft}{label}" if zh else f"draft {d.draft} ({d.draft_label})")
    head = f"- {_md(d.when)} {kind[0] if zh else kind[1]}（{d.email_id}）：" if zh else f"- {_md(d.when)} {kind[1]} ({d.email_id}): "
    return head + ("；" if zh else "; ").join(parts)


def missing_fields(picked: list[ReportDigest], wanted: set[str]) -> list[str]:
    """Wanted fields that no selected row carries."""
    seen = set()
    for d in picked:
        if d.speed_day or d.speed_avg:
            seen.add("speed")
        if d.consumption:
            seen.add("consumption")
        if d.wind or d.sea or d.sky or d.current:
            seen.add("weather")
        if d.draft:
            seen.add("draft")
    return sorted(wanted - seen)


def has_current(picked: list[ReportDigest]) -> bool:
    return any(d.current for d in picked)
