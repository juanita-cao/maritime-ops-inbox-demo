"""Helpers for writing a vessel's timeline: ids are issued in order, times are written as local
yyyy-mm-dd HH:MM (+08:00 unless a vessel says otherwise)."""

from mockdata.ledger import Event, Ledger, Party, Truth, Voyage

T_REPORT = "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)"


class Builder:
    def __init__(self, vessel: str, prefix: str, tz: str = "+08:00"):
        self.vessel, self.prefix, self.tz = vessel, prefix, tz
        self.parties: list[Party] = []
        self.voyages: list[Voyage] = []
        self.events: list[Event] = []
        self.truths: list[Truth] = []
        self.discrepancies: list[str] = []

    def iso(self, local: str) -> str:
        return local.replace(" ", "T") + ":00" + self.tz

    def party(self, code: str, name: str, role: str, domain: str) -> None:
        self.parties.append(Party(code=code, name=name, role=role, domain=domain))

    def voyage(self, no: str, status: str, cp_ref: str, load_port: str, disch_port: str, cargo: str, qty: float,
               sailed: str | None = None, eta: str | None = None) -> None:
        self.voyages.append(Voyage(no=no, status=status, cp_ref=cp_ref, load_port=load_port, disch_port=disch_port, cargo=cargo,
                                   qty_mt=qty, sailed=self.iso(sailed) if sailed else None, eta=self.iso(eta) if eta else None))

    def email(self, when: str, event_type: str, sender: str, to: list[str], thread: str, subject: str, voyage: str | None,
              reply_to: str | None = None, scenario: str | None = None, note: str = "", **facts) -> str:
        eid = f"{self.prefix}{len(self.events) + 1:03d}"
        self.events.append(Event(id=eid, time=self.iso(when), event_type=event_type, sender=sender, receivers=to, thread=thread,
                                 subject=subject, voyage=voyage, reply_to=reply_to, scenario=scenario, facts=facts, note=note))
        return eid

    def truth(self, scenario: str, question: str, answer: str, evidence: list[str]) -> None:
        self.truths.append(Truth(scenario=scenario, question=question, answer=answer, evidence=evidence))

    def ledger(self) -> Ledger:
        """Events in time order with ids renumbered to match (replies and truths follow the new ids)."""
        ordered = sorted(self.events, key=lambda e: e.time)
        new = {e.id: f"{self.prefix}{i + 1:03d}" for i, e in enumerate(ordered)}
        events = [e.model_copy(update={"id": new[e.id], "reply_to": new.get(e.reply_to or "")}) for e in ordered]
        truths = [t.model_copy(update={"evidence": [new[x] for x in t.evidence]}) for t in self.truths]
        return Ledger(vessel=self.vessel, parties=self.parties, voyages=self.voyages, events=events, truths=truths,
                      discrepancies=self.discrepancies)
