"""Skeleton emails from the ledger (docs/design_mock_data.md 5): header block, body, signature and quoted
history in the layout E1 reads. Reports (noon, sailing, arrival) use the fixed layouts that
`report_digest` reads; other mail is a plain statement of the event's note and facts, which the polish
step later rewrites in a human voice (the skeleton alone is readable and complete). Pure functions: the
same ledger always gives the same text."""

import re
from dataclasses import dataclass

from mockdata.ledger import Event, Ledger, Party

MAX_QUOTE_DEPTH = 3
_UNITS = (("_usd_mt", " USD per mt"), ("_usd_day", " USD per day"), ("_total_usd", " USD"), ("_usd", " USD"), ("_pct", " %"), ("_mt_h", " mt/h"),
          ("_mt_day", " mt/day"), ("_mt", " mt"), ("_kn", " kn"), ("_hours", " hours"), ("_days", " days"), ("_nm", " nm"))
_HIDDEN = ("pos_text", "eta_", "rob_", "speed_", "wind_", "sea_", "cons_", "draft_")  # report fields are laid out, not listed


@dataclass
class Ctx:
    ledger: Ledger
    vessel_name: str
    ids: dict[str, str]  # ledger event id -> E### email id

    @property
    def parties(self) -> dict[str, Party]:
        return {p.code: p for p in self.ledger.parties}

    @property
    def events(self) -> dict[str, Event]:
        return {e.id: e for e in self.ledger.events}


def mailbox(party: Party) -> str:
    return f"mail01@{party.domain}"


def assign_ids(ledgers: list[Ledger]) -> dict[str, str]:
    """E001 … in time order across the whole fleet, like the real corpus (the chat links E### ids)."""
    events = sorted((e for lg in ledgers for e in lg.events), key=lambda e: (e.time, e.id))
    return {e.id: f"E{i + 1:03d}" for i, e in enumerate(events)}


def _stamp(iso: str) -> str:
    date, rest = iso.split("T")
    return f"{date} {rest[:8]} UTC{rest[8:]}"


def _label(key: str, value) -> str:
    text = key
    unit = ""
    for suffix, u in _UNITS:
        if key.endswith(suffix):
            text, unit = key[: -len(suffix)], u
            break
    name = text.replace("_", " ").strip().capitalize()
    shown = f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 10000 else str(value)
    return f"{name}: {shown}{unit}"


def _greeting(ctx: Ctx, e: Event) -> str:
    to = ctx.parties[e.receivers[0]]
    return {"owner": "Dear Owners,", "charterer": "Dear Charterers,", "sub_charterer": "Dear Sirs,", "master": "Dear Captain,", "operator": "Dear Colleagues,",
            "port_agent": "Dear Sirs,", "pni_correspondent": "Dear Sirs,", "surveyor": "Dear Sirs,", "broker": "Dear Sirs,"}.get(to.role, "Dear Sirs,")


def _signature(ctx: Ctx, e: Event) -> str:
    p = ctx.parties[e.sender]
    if p.role == "master":
        return f"Best regards,\n{p.name.replace('Master, ', 'Master ')}"
    return f"Best regards,\n{p.name}"


def _sentence(note: str) -> str:
    note = note.strip()
    return (note[:1].upper() + note[1:]).rstrip(".") + "." if note else ""


def _num(facts: dict, key: str, default: float) -> float:
    v = facts.get(key)
    return float(v) if isinstance(v, int | float) else default


def _local(iso: str) -> tuple[str, str]:
    """('9 Oct 2026', '12:20')"""
    y, m, d = iso[:10].split("-")
    mon = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[int(m) - 1]
    return f"{int(d)} {mon} {y}", iso[11:16]


def _is_master_report(ctx: Ctx, e: Event) -> str | None:
    if ctx.parties[e.sender].role != "master":
        return None
    s = e.subject.upper()
    for key in ("NOON REPORT", "SAILING REPORT", "ARRIVAL REPORT"):
        if key in s:
            return key.split()[0].lower()
    return None


def _report_body(ctx: Ctx, e: Event, kind: str) -> str:
    f = e.facts
    date, hhmm = _local(e.time)
    vessel = ctx.ledger.vessel
    rob = f.get("rob_vlsfo")
    rob_line = f"ROB: VLSFO {rob} mt, LSMGO {f.get('rob_lsmgo', 60.0)} mt" if rob is not None else None
    eta = next((str(v) for k, v in f.items() if k.startswith("eta_")), None)
    lines = ["Good day,", ""]
    if kind == "noon":
        spd = _num(f, "speed_log_kn", 11.5)
        cons = _num(f, "cons_vlsfo_mt", 27.0)
        wd, force, sea = f.get("wind_dir", "NE"), int(_num(f, "wind_force", 3)), _num(f, "sea_m", 1.0)
        sky = "Fine" if force <= 3 else "Cloudy" if force <= 5 else "Overcast"
        avg = _num(f, "speed_avg_kn", spd - 0.1)
        lines += [f"Noon report, {vessel}, {e.voyage}.", f"Dd: {date}", f"Position: {f.get('pos_text', 'at sea')} at 1200 LT",
                  f"Course/avg spd/rpm/eng slip: 090 / {avg:.1f} / 72 / 3.0",
                  f"Daily GPS speed / Log speed: {spd + 0.1:.1f} / {spd:.1f}", f"Average GPS speed / Log Speed: {avg + 0.1:.1f} / {avg:.1f}",
                  f"IFO Consumed/LSMGO consumed fm last report: VLSFO {cons:.1f} mt LSMGO 0.0 mt", f"Wind direction/force/sea cond/vis: {wd} / {force} / {sea} M / Good",
                  f"Weather condition: {wd} / {force} {sky}"]
        if rob_line:
            lines.append(rob_line)
        if eta:
            lines.append(f"ETA: {eta} LT")
        lines.append("Remarks: Vessel proceeding normally.")
    elif kind == "sailing":
        lines += [f"Sailing report, {vessel}, {e.voyage}.", f"Dd: {date}", f"Sailed at {hhmm} LT.", f"Cargo on board: {f.get('cargo_qty_mt', '')} mt".replace(" on board:  mt", " on board: as per B/L")]
        m = re.match(r"F\s*([\d.]+)\s*/\s*A\s*([\d.]+)", str(f.get("draft_sailing", "")))
        if m:
            lines.append(f"Sailing Draft: F {m.group(1)} m / A {m.group(2)} m")
        if rob_line:
            lines.append(rob_line)
        if eta:
            lines.append(f"ETA: {eta} LT")
    else:
        lines += [f"Arrival report, {vessel}, {e.voyage}.", f"Dd: {date}", f"Arrived at {hhmm} LT.", f"NOR tendered: {f.get('nor_tendered', 'on arrival')}"]
        if rob_line:
            lines.append(rob_line)
    return "\n".join(lines)


def _plain_body(ctx: Ctx, e: Event) -> str:
    facts = [_label(k, v) for k, v in e.facts.items() if not k.startswith(_HIDDEN)]
    parts = [_greeting(ctx, e), "", _sentence(e.note)]
    if facts:
        parts += ["", *[f"- {x}" for x in facts]]
    return "\n".join(parts)


def _body(ctx: Ctx, e: Event) -> str:
    kind = _is_master_report(ctx, e)
    return _report_body(ctx, e, kind) if kind else _plain_body(ctx, e)


def _header(ctx: Ctx, e: Event) -> str:
    sender = ctx.parties[e.sender]
    to = [mailbox(ctx.parties[c]) for c in e.receivers[:1]]
    cc = [mailbox(ctx.parties[c]) for c in e.receivers[1:]]
    lines = [f"From: {mailbox(sender)}", f"Sent: {_stamp(e.time)}", f"To: {'; '.join(to)}"]
    if cc:
        lines.append(f"Cc: {'; '.join(cc)}")
    lines.append(f"Subject: {e.subject}")
    return "\n".join(lines)


def render(ctx: Ctx, e: Event, depth: int = 0, bodies: dict[str, str] | None = None) -> str:
    """The email as E1 reads it: header, blank line, body, signature, then the quoted history of the mail it answers.
    `bodies` replaces the generated body for an event (the polish step's output)."""
    body = (bodies or {}).get(e.id) or _body(ctx, e)
    text = f"{_header(ctx, e)}\n\n{body}\n\n{_signature(ctx, e)}"
    if e.reply_to and depth < MAX_QUOTE_DEPTH:
        parent = ctx.events[e.reply_to]
        quoted = render(ctx, parent, depth + 1, bodies)
        text += "\n\n-----Original Message-----\n" + quoted
    return text


def render_all(ledgers: list[Ledger], names: dict[str, str], bodies: dict[str, str] | None = None) -> dict[str, str]:
    """E-id -> the full text of that email, for every event of every ledger."""
    ids = assign_ids(ledgers)
    out = {}
    for lg in ledgers:
        ctx = Ctx(lg, names.get(lg.vessel, lg.vessel), ids)
        for e in lg.events:
            out[ids[e.id]] = render(ctx, e, bodies=bodies)
    return out
