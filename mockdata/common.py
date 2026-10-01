"""Shared pieces of the medium and light vessels: the operator, party creation with a mailbox derived from
the name, and a run of daily noon reports."""

import re

from mockdata.builder import T_REPORT, Builder

OP = "OPR-01"
BROKER = "CPY-14"


def party(b: Builder, code: str, name: str, role: str) -> str:
    b.party(code, name, role, re.sub(r"[^a-z0-9]+", "", name.lower().replace("master, mv ", "vsl")) + ".example")
    return code


def operator(b: Builder) -> None:
    b.party(OP, "Meridian Fleet Management", "operator", "meridianfleet.example")


def broker(b: Builder) -> None:
    b.party(BROKER, "Pelham Shipbrokers", "broker", "pelhambrokers.example")


def noons(b: Builder, vessel: str, voyage: str, master: str, to: list[str], days: list[tuple], eta_key: str, eta: str, thread: str) -> None:
    """days: (date, rob_vlsfo, speed_log_kn, consumption_mt, wind_force, sea_m, position)."""
    for date, rob, spd, cons, force, sea, pos in days:
        b.email(f"{date} 12:20", T_REPORT, master, to, thread, f"{vessel} NOON REPORT {date}", voyage, note="daily noon report", rob_vlsfo=rob,
                speed_log_kn=spd, speed_avg_kn=round(spd - 0.1, 1), cons_vlsfo_mt=cons, pos_text=pos, wind_force=force, sea_m=sea, **{eta_key: eta})
