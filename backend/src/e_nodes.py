"""E nodes of the DEP (design_backend.md section 4). One node, one function; every input is an
argument (section 13), so nothing here reads the store, the knowledge base or the clock."""

import re
from collections.abc import Callable

from pydantic import ValidationError
from datetime import date, datetime, timedelta, timezone, tzinfo

from src.kb_loader import KbError, KnowledgeBase
from src import prompts
from src.llm_client import LlmClient, LlmError
from src import d_nodes
from src.store import Store
from src.schemas import (
    ActionCandidate,
    ActionCandidates,
    DateFact,
    EventCandidate,
    EventCandidates,
    EventDecision,
    Evidence,
    ExtractedEntities,
    FactChange,
    FactChanges,
    FactLookup,
    FactRecord,
    Finding,
    HeldRecord,
    Lane,
    Mention,
    NeedsActionDecision,
    ParsedEmail,
    PartyRef,
    PartyRoles,
    Proposal,
    QuantityFact,
    RankedActions,
    RawEmail,
    Reference,
    SanitizationCheck,
    SavedProposal,
    TaskDisposition,
    ThreadIndex,
    ThreadIndexEntry,
    ThreadRef,
    TraceStep,
    VesselMatch,
    VoyageMatch,
)


class ParseError(ValueError):
    """E1 hard fail: the email has no text to work on."""


# --- E1 e1_parse_email ------------------------------------------------------------

# Header keys in English and Chinese, mapped to one field name. Any order is accepted.
_HEADER_KEYS = {
    "from": "sender",
    "发件人": "sender",
    "sent": "sent",
    "date": "sent",
    "发送时间": "sent",
    "日期": "sent",
    "to": "to",
    "收件人": "to",
    "cc": "cc",
    "抄送": "cc",
    "subject": "subject",
    "主题": "subject",
    "attachments": "attachments",
    "attachment": "attachments",
    "附件": "attachments",
}
_KEY_LINE = re.compile(r"^\s*([A-Za-z]+|[一-鿿]+)\s*[:：]\s*(.*)$")
_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SPACE_AT_PUNCT = re.compile(r"\s*([^\w\s])\s*")
_SUBJECT_PREFIX = re.compile(r"^\s*(?:re|fw|fwd|回复|答复|转发)\s*(?:\[\d+\])?\s*[:：]\s*", re.I)

# Quoted history starts at an "Original Message" line, or at a From line followed within five
# lines by a sent-time line (a To/Cc block alone is body text, E1-S07).
_ORIGINAL = re.compile(r"^\s*-{2,}\s*(?:original message|原始邮件)\s*-{2,}\s*$", re.I)
_QUOTE_FROM = re.compile(r"^\s*(?:from|发件人)\s*[:：]", re.I)
_QUOTE_TIME = re.compile(r"^\s*(?:sent|date|发送时间|日期)\s*[:：]", re.I)
_QUOTE_SUBJECT = re.compile(r"^\s*(?:subject|主题)\s*[:：]\s*(.+?)\s*$", re.I)
_SEPARATOR = re.compile(r"^[\s_\-=*]*$")

# A closing line is made only of these words and punctuation, and holds at least one anchor
# ("Best regards,", "B.Rgds", "Thanks & B.Rgds", "Tks@B.RGDS"). "Thanks, noted." is not one.
_CLOSING_WORDS = {
    "best", "kind", "warm", "warmest", "regards", "regard", "rgds", "brgds", "b", "br",
    "thanks", "thank", "thx", "tks", "you", "many", "and", "with", "cheers", "yours",
    "faithfully", "sincerely", "truly",
}  # fmt: skip
_CLOSING_ANCHORS = {
    "regards", "regard", "rgds", "brgds", "br", "thanks", "thank", "thx", "tks", "cheers",
    "faithfully", "sincerely",
}  # fmt: skip
_CLOSING_CN = ("此致", "谢谢", "多谢", "顺祝商祺", "祝好")
_POSTSCRIPT = re.compile(r"^\s*(?:p\.\s?s\.?|ps)(?:\s*[:.,\-]|\s|$)", re.I)

# A signature block after the closing line: a few short lines that are not sentences.
MAX_SIGNATURE_LINES = 12  # a master's block runs to about 9 lines
MAX_SIGNATURE_WORDS = 6
MAX_SIGNATURE_CHARS = 60
# Contact lines of a signature may be long ("EMAIL: ...<mailto:...> (Attachment available)").
_CONTACT_LINE = re.compile(
    r"^\s*(?:e-?mail|tel|mob|mobile|fax|iridium|skype|web|wechat)\b.*[:：]", re.I
)
_COMPANY_END = re.compile(r"\b(?:ltd|co|inc|corp|llc|pte|gmbh|s\.a)\.$", re.I)
# Legal boilerplate below an email [AMENDMENT 2026-09-26 T2.1-f]. Only set phrases, so that a
# business line such as "keep the rate confidential" stays in new_text.
_DISCLAIMER = re.compile(
    r"privileged and confidential|confidential and/or privileged|may be privileged"
    r"|intended recipient|intended solely for|respects your data privacy|privacy policy"
    r"|scanned for (?:email|viruses|e-mail)|company registration information|^\s*disclaimer\b",
    re.I,
)

SHORT_TEXT_CHARS = 300  # attachment_dependent border (G5): 300 is short, 301 is not

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    )
}
_TIME = r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?m\.?)?"
_DATE_FORMATS = (
    # 2026-07-30 14:48:00 (the corpus form, followed by UTC+08:00)
    ("ymd", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T]+" + _TIME, re.I)),
    # 2026年7月30日 星期四 14:48
    ("ymd", re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\D*?" + _TIME, re.I)),
    # Thursday, July 30, 2026 2:48 PM / July 30th 2026 at 2:48 pm
    ("mdy", re.compile(r"([a-z]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}),?\s+(?:at\s+)?" + _TIME, re.I)),
    # 30 July 2026 14:48
    ("dmy_name", re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,})\.?,?\s+(\d{4}),?\s+(?:at\s+)?" + _TIME, re.I)),
    # 30/07/26 14:48 (day first, as in the corpus)
    ("dmy", re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})\s+" + _TIME, re.I)),
)  # fmt: skip
_OFFSET = re.compile(r"(?:(?:UTC|GMT)\s*|(?<=\d)\s?)([+-])(\d{1,2})(?::?(\d{2}))?\s*$", re.I)
MAX_OFFSET_HOURS = 14  # real UTC offsets run from -12:00 to +14:00
_ZULU = re.compile(r"(?<=\d)Z\s*$|\b(?:UTC|GMT)\s*$", re.I)


def _parse_sent_time(value: str, default_offset: tzinfo) -> tuple[datetime | None, bool]:
    """Return (time, offset_assumed). An unreadable value gives (None, False)."""
    for kind, pattern in _DATE_FORMATS:
        m = pattern.search(value)
        if not m:
            continue
        g = m.groups()
        try:
            if kind == "ymd":
                year, month, day = int(g[0]), int(g[1]), int(g[2])
            elif kind == "mdy":
                year, month, day = int(g[2]), _MONTHS[g[0][:3].lower()], int(g[1])
            elif kind == "dmy_name":
                year, month, day = int(g[2]), _MONTHS[g[1][:3].lower()], int(g[0])
            else:
                year, month, day = int(g[2]), int(g[1]), int(g[0])
                year += 2000 if year < 100 else 0
            hour, minute, second = int(g[3]), int(g[4]), int(g[5] or 0)
            meridiem = (g[6] or "").replace(".", "").lower()
            if meridiem:
                if not 1 <= hour <= 12:
                    return None, False  # "13:48 PM" or "00:48 PM" is not a time
                hour = hour % 12 + (12 if meridiem == "pm" else 0)
            # datetime() rejects hour 24, minute 60 and 30 February; nothing is normalised
            local = datetime(year, month, day, hour, minute, second)
        except (KeyError, ValueError):
            return None, False
        rest = value[m.end() :]
        offset = _OFFSET.search(rest)
        if offset:
            hours, minutes = int(offset.group(2)), int(offset.group(3) or 0)
            if hours > MAX_OFFSET_HOURS or minutes > 59:
                return None, False  # checked here: timedelta would carry 08:99 into 09:39
            sign = -1 if offset.group(1) == "-" else 1
            delta = timedelta(hours=hours, minutes=minutes)
            return local.replace(tzinfo=timezone(sign * delta)), False
        if _ZULU.search(rest):
            return local.replace(tzinfo=timezone.utc), False
        return local.replace(tzinfo=default_offset), True
    return None, False


def _addresses(value: str) -> list[str]:
    found = [a.lower() for a in _ADDRESS.findall(value)]
    if found:
        return found
    return [part.strip() for part in value.split(";") if part.strip()]


def normalise_subject(subject: str) -> str:
    """Subject without Re:/Fw: prefixes (English and Chinese), case and spacing differences,
    including spaces next to punctuation ("VSL-02// NOON" equals "VSL-02//noon") (E1 and E2)."""
    previous = None
    while previous != subject:
        previous, subject = subject, _SUBJECT_PREFIX.sub("", subject, count=1)
    subject = _SPACE_AT_PUNCT.sub(r"\1", " ".join(subject.split()))
    return subject.lower()


def _is_closing(line: str) -> bool:
    text = line.strip().lower()
    if not text:
        return False
    if text.startswith(_CLOSING_CN):
        return len(text) <= 8
    if not re.fullmatch(r"[a-z\s,.!&@/+\-]+", text):
        return False
    words = re.findall(r"[a-z]+", text)
    return (
        0 < len(words) <= 6
        and all(w in _CLOSING_WORDS for w in words)
        and any(w in _CLOSING_ANCHORS for w in words)
    )


def _is_signature_line(line: str) -> bool:
    """A name, role or company line ("PER-03", "Operations, CPY-01"), not a sentence. When in
    doubt the line counts as a sentence, so business text stays in new_text."""
    text = line.strip()
    if not text or _is_closing(text) or _CONTACT_LINE.match(text):
        return True
    if len(text.split()) > MAX_SIGNATURE_WORDS or len(text) > MAX_SIGNATURE_CHARS:
        return False
    return not text.endswith((".", "?", "!", ":", ";", "？", "。", "！", "：")) or bool(
        _COMPANY_END.search(text)
    )


def _signature_start(lines: list[str]) -> int | None:
    """Index where the signature block or postscript starts, or None. A closing line counts
    only when real text stands above it (E1-S14) and everything after it, up to a postscript,
    looks like a signature block (review 2026-09-26: "Thanks" followed by a sentence is body).
    A legal disclaimer starts the signature text as well [AMENDMENT 2026-09-26 T2.1-f]."""

    def has_text_above(i: int) -> bool:
        return any(line.strip() and not _is_closing(line) for line in lines[:i])

    disclaimer = next(
        (i for i, line in enumerate(lines) if _DISCLAIMER.search(line) and has_text_above(i)),
        None,
    )

    def block_follows(i: int) -> bool:
        after = []
        for line in lines[i + 1 : disclaimer]:
            if _POSTSCRIPT.match(line):
                break
            if line.strip():
                after.append(line)
        return len(after) <= MAX_SIGNATURE_LINES and all(_is_signature_line(x) for x in after)

    candidates = [] if disclaimer is None else [disclaimer]
    closing = [
        i
        for i, line in enumerate(lines[:disclaimer])
        if _is_closing(line) and has_text_above(i) and block_follows(i)
    ]
    if closing:
        start = closing[-1]
        # Take in closing lines directly above ("Thanks" over "Best regards").
        above = start - 1
        while above >= 0 and (not lines[above].strip() or _is_closing(lines[above])):
            if lines[above].strip():
                start = above
            above -= 1
        candidates.append(start)
    postscript = [
        i for i, line in enumerate(lines) if _POSTSCRIPT.match(line) and has_text_above(i)
    ]
    if postscript:
        candidates.append(postscript[0])
    return min(candidates) if candidates else None


def _quote_start(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if _ORIGINAL.match(line):
            return i
        if _QUOTE_FROM.match(line) and any(_QUOTE_TIME.match(x) for x in lines[i + 1 : i + 6]):
            return i
    return None


def _split_header(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """The header is the top block up to the first blank line, and only if it starts with a
    header line; otherwise the whole text is body. A line without a known key continues the
    field above it (wrapped recipient lists)."""
    fields: dict[str, str] = {}
    first = _KEY_LINE.match(lines[0]) if lines else None
    if not first or first.group(1).lower() not in _HEADER_KEYS:
        return fields, lines
    current = None
    for i, line in enumerate(lines):
        if not line.strip():
            return fields, lines[i + 1 :]
        m = _KEY_LINE.match(line)
        key = m.group(1).lower() if m else None
        if key in _HEADER_KEYS:
            current = _HEADER_KEYS[key]
            fields.setdefault(current, m.group(2).strip())
        elif m:
            current = None  # a header we do not use (Importance, Priority, ...)
        elif current:
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields, []


def e1_parse_email(
    raw: RawEmail, own_domains: frozenset[str], default_utc_offset: tzinfo
) -> ParsedEmail:
    """E1 Extract: split the raw email into header fields, new text, signature and quoted
    history (design_backend.md E1 row, amendments F3, F8, F14, G5 and T2.1)."""
    lines = raw.text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\n").split("\n")
    fields, body = _split_header(lines)
    flags: list[str] = []

    sender_list = _addresses(fields.get("sender", ""))
    sender = sender_list[0] if sender_list else ""
    if not sender:
        flags.append("no_sender")
    subject = fields.get("subject", "")
    if not subject:
        flags.append("no_subject")
    sent_time, assumed = _parse_sent_time(fields.get("sent", ""), default_utc_offset)
    if sent_time is None:
        flags.append("no_sent_time")
    elif assumed:
        flags.append("sent_time_offset_assumed")
    domain = sender.rsplit("@", 1)[1] if "@" in sender else ""
    direction = "Outbound" if domain in {d.lower() for d in own_domains} else "Inbound"

    if not any(line.strip() for line in body):
        raise ParseError(f"{raw.email_id}: empty body")
    quote_at = _quote_start(body)
    new_lines = body if quote_at is None else body[:quote_at]
    quoted_text = "" if quote_at is None else "\n".join(body[quote_at:]).strip()
    while new_lines and _SEPARATOR.match(new_lines[-1]):
        new_lines = new_lines[:-1]  # blank lines and the "____" line above a quoted header
    sig_at = _signature_start(new_lines)
    new_text = "\n".join(new_lines if sig_at is None else new_lines[:sig_at]).strip()
    signature_text = "" if sig_at is None else "\n".join(new_lines[sig_at:]).strip()
    if not new_text:
        raise ParseError(f"{raw.email_id}: no new text above the quoted history")

    quoted_subjects: list[str] = []
    for line in quoted_text.split("\n"):
        m = _QUOTE_SUBJECT.match(line)
        if m and m.group(1) not in quoted_subjects:
            quoted_subjects.append(m.group(1))
    attachment_names = [a.strip() for a in fields.get("attachments", "").split(";") if a.strip()]

    return ParsedEmail(
        email_id=raw.email_id,
        subject=subject,
        subject_norm=normalise_subject(subject),
        sent_time=sent_time,
        direction=direction,
        sender=sender,
        receivers=_addresses(fields.get("to", "")) + _addresses(fields.get("cc", "")),
        new_text=new_text,
        signature_text=signature_text,
        attachment_dependent=bool(attachment_names) and len(new_text) <= SHORT_TEXT_CHARS,
        attachment_names=attachment_names,
        quoted_text=quoted_text,
        quoted_subjects=quoted_subjects,
        parse_flags=flags,
    )


# --- E2 e2_derive_thread_key ------------------------------------------------------

_NO_TIME = datetime.max.replace(tzinfo=timezone.utc)  # entries without a time sort last


def _order(sent_time: datetime | None, email_id: str) -> tuple[datetime, str]:
    """Chronological order; an email without a time sorts after the dated ones, then by id."""
    return (sent_time or _NO_TIME, email_id)


def _entry_order(entry: ThreadIndexEntry) -> tuple[datetime, str]:
    return _order(entry.sent_time, entry.email_id)


def _hint_order(entry: ThreadIndexEntry) -> tuple[int, float, str]:
    """For the vessel and voyage hint: dated entries newest first; undated ones only after all
    dated ones (they are not known to be newer), by id (review 2026-09-26)."""
    if entry.sent_time is None:
        return (1, 0.0, entry.email_id)
    return (0, -entry.sent_time.timestamp(), entry.email_id)


def e2_derive_thread_key(email: ParsedEmail, index: ThreadIndex) -> ThreadRef:
    """E2 Transform: put the email in a thread (design_backend.md E2 row, amendments F2 and
    T2.2). Keys are the normalised subject and quoted subjects; sharing one key links."""
    keys = {email.subject_norm} | {normalise_subject(q) for q in email.quoted_subjects}
    keys.discard("")
    linked = {
        entry.thread_id
        for entry in index.entries
        if keys & ({entry.subject_norm} | set(entry.quoted_subjects_norm))
    }
    if not linked:
        return ThreadRef(
            thread_id=f"T-{email.email_id}", is_new_thread=True, member_email_ids=[email.email_id]
        )

    # the email itself is never counted twice (a retry may find it in the index already)
    members = sorted(
        (e for e in index.entries if e.thread_id in linked and e.email_id != email.email_id),
        key=_entry_order,
    )
    first_time: dict[str, datetime] = {}
    for entry in members:
        first_time.setdefault(entry.thread_id, entry.sent_time or _NO_TIME)
    kept = min(linked, key=lambda thread_id: (first_time.get(thread_id, _NO_TIME), thread_id))

    vessel = voyage = None
    for entry in sorted(members, key=_hint_order):
        if vessel is None and entry.vessel_code:
            vessel = entry.vessel_code
        if vessel is not None and entry.vessel_code == vessel and entry.voyage_no:
            voyage = entry.voyage_no
            break
    ordered = sorted(
        [(_entry_order(e), e.email_id) for e in members]
        + [(_order(email.sent_time, email.email_id), email.email_id)]
    )
    return ThreadRef(
        thread_id=kept,
        is_new_thread=False,
        member_email_ids=[email_id for _, email_id in ordered],
        thread_vessel=vessel,
        thread_voyage=voyage,
        merged_thread_ids=sorted(linked - {kept}),
    )


# --- E3 e3_resolve_sender ---------------------------------------------------------


def _party_ref(address: str, kb: KnowledgeBase) -> PartyRef:
    """Table lookup: contact, then its party's role and confidence. Never guessed. An unknown
    address or a contact without a party is Other; a contact that names a party missing from the
    knowledge base is a broken table (load_kb rejects it; this guards a KB built another way)."""
    contact = kb.contacts.get(address.strip().lower())
    if contact is None or contact.party_code is None:
        return PartyRef(address=address)
    party = kb.parties.get(contact.party_code)
    if party is None:
        raise KbError(
            [
                f"contact {contact.contact_code} names party {contact.party_code}, which is not in the knowledge base"
            ]
        )
    return PartyRef(
        address=address, party_code=party.party_code, role=party.role, confidence=party.confidence
    )


def e3_resolve_sender(email: ParsedEmail, kb: KnowledgeBase) -> PartyRoles:
    """E3 Select: sender and receiver roles from the coded contacts (design_backend.md E3 row,
    [AMENDMENT 2026-09-26 T2.3]). low_confidence looks at the sender only."""
    sender = _party_ref(email.sender, kb)
    return PartyRoles(
        sender=sender,
        receivers=[_party_ref(address, kb) for address in email.receivers],
        low_confidence=sender.role == "Other" or sender.confidence == "unknown",
    )


# --- E4 e4_check_sanitized --------------------------------------------------------

# Coded forms that are allowed, checked on the whole token (review 2026-09-26): mailNN@co-NN.example,
# mailNN@example.com, PHONE-NN, ADDR-NN, hosts under a coded domain, and the four link-rewriting
# hosts of the corpus with their path replaced by "[link removed]".
_E4_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
# [AMENDMENT 2026-10-01, docs/design_mock_data.md] any host under the reserved .example top-level domain (RFC 2606) is
# coded as well: it cannot be a real address, and the mock dataset uses readable fictional company domains.
_E4_CODED_EMAIL = re.compile(r"mail\d+@(?:co-\d+\.example|[a-z0-9-]+\.example|example\.com)", re.I)
_E4_CODED_DOMAIN = re.compile(r"(?:^|\.)(?:co-\d+\.example|[a-z0-9-]+\.example|example\.com)$", re.I)
# Mail-software artefacts (F1b, E4-S06), as whole patterns: "Tks@B.RGDS" and an image content id
# written "cid:image001.png@01DB1234.5A6B7C80". Any other address on such a domain is a finding.
_E4_ARTEFACT_EMAIL = re.compile(r"tks@b\.rgds", re.I)
_E4_CONTENT_ID = re.compile(r"image\d+\.(?:png|jpe?g|gif)@[0-9a-f]{8}\.[0-9a-f]{8}", re.I)
_E4_REWRITTEN_LINK = re.compile(
    r"https?://(?:s3\.amazonaws\.com|bucket\d+-[a-z]+\.s3\.[a-z0-9-]+\.amazonaws\.com"
    r"|url-scan\.centerasecurity\.com|www\.mimecast\.com)/\[link removed\](?![A-Za-z0-9])",
    re.I,
)
_E4_PHONES = (
    re.compile(r"\+\s?\d{1,3}[\s\-]?\(?\d[\d\s\-()]{6,}\d"),  # with a plus sign
    re.compile(r"(?<![\w-])(?:86-?)?1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)"),  # mainland mobile
    re.compile(r"(?<![\w.])\d{2,4}-\d{2,4}-\d{6,8}(?!\d)"),  # without a plus sign
)
# [AMENDMENT 2026-10-01] identity numbers: a Chinese resident ID (18 digits, last may be X; old
# 15-digit form) and passport numbers (E/G + 8 digits, E/G + letter + 7 digits). One ID number
# with its holder's name survived the desensitization in E063 and reached a chat answer.
_E4_ID_NUMBERS = (
    re.compile(r"(?<![\dA-Za-z])(?:\d{17}[\dXx]|\d{15})(?![\dA-Za-z])"),
    re.compile(r"(?<![A-Za-z0-9])(?:[EGDSP]\d{8}|[EG][A-Z]\d{7})(?![A-Za-z0-9])"),
)
_E4_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.I)
_E4_ADD_LINE = re.compile(r"(?im)^[ \t]*(?:add|addr|address)[ \t]*[:：][ \t]*(.+)$")
_E4_CODED_ADDRESS = re.compile(r"\bADDR-\d+\b")
_E4_STREET = re.compile(
    r"\b(?:Road|Street|Avenue|Boulevard)\b|#\d{2}-\d{2}|\bSingapore\s+\d{6}\b", re.I
)


def _scan_text(text: str) -> list[tuple[str, int, int]]:
    """(kind, start, end) of every value that is not in coded form."""
    hits: list[tuple[str, int, int]] = []
    for m in _E4_EMAIL.finditer(text):
        token = m.group(0)
        content_id = text[max(0, m.start() - 4) : m.start()].lower() == "cid:"
        if not (
            _E4_CODED_EMAIL.fullmatch(token)
            or _E4_ARTEFACT_EMAIL.fullmatch(token)
            or (content_id and _E4_CONTENT_ID.fullmatch(token))
        ):
            hits.append(("email", m.start(), m.end()))
    for pattern in _E4_PHONES:
        hits += [("phone", m.start(), m.end()) for m in pattern.finditer(text)]
    for m in _E4_URL.finditer(text):
        host = re.sub(r"^(?:https?://)", "", m.group(0), flags=re.I).split("/")[0].split(":")[0]
        rewritten = _E4_REWRITTEN_LINK.match(text, m.start())
        if not (rewritten or _E4_CODED_DOMAIN.search(host)):
            hits.append(("url", m.start(), m.end()))
    for m in _E4_ADD_LINE.finditer(text):
        rest = _E4_CODED_ADDRESS.sub("", m.group(1))
        if re.search(r"[A-Za-z0-9一-鿿]", rest):
            hits.append(("address", m.start(), m.end()))
    hits += [("address", m.start(), m.end()) for m in _E4_STREET.finditer(text)]
    for pattern in _E4_ID_NUMBERS:
        hits += [("id_number", m.start(), m.end()) for m in pattern.finditer(text)]
    return hits


def _count_findings(hits: list[tuple[str, int, int]]) -> dict[str, int]:
    """Overlapping hits of one kind count once ("Add: 88 Harbour Road" is one address)."""
    counts: dict[str, int] = {}
    for kind in ("email", "phone", "url", "address", "id_number"):
        spans = sorted((a, b) for k, a, b in hits if k == kind)
        end = -1
        for a, b in spans:
            if a >= end:
                counts[kind] = counts.get(kind, 0) + 1
            end = max(end, b)
    return counts


def e4_check_sanitized(email: ParsedEmail) -> SanitizationCheck:
    """E4 Detect, the data boundary (design_backend.md E4 row, amendments F1, F1b). Fails
    closed: a finding blocks the LLM path; a broken check is check_failed, never clean."""
    try:
        texts = [
            email.subject,
            email.new_text,
            email.signature_text,
            email.quoted_text,
            email.sender,
            *email.receivers,
            *email.attachment_names,
        ]
        counts: dict[str, int] = {}
        for text in texts:
            for kind, n in _count_findings(_scan_text(text)).items():
                counts[kind] = counts.get(kind, 0) + n
    except Exception as exc:  # noqa: BLE001 - any failure of the check itself is check_failed
        return SanitizationCheck(status="check_failed", error=f"{type(exc).__name__}: {exc}")
    if not counts:
        return SanitizationCheck(status="clean")
    return SanitizationCheck(
        status="blocked_unsanitized",
        findings=[
            Finding(kind=k, count=counts[k])
            for k in ("email", "phone", "url", "address", "id_number")
            if k in counts
        ],  # fixed order
    )


# --- E5 e5_extract_entities -------------------------------------------------------

_E5_VESSEL = re.compile(r"(?<![\w-])VSL-\d{2}\b")  # not inside OWN-VSL-12 (T2.6)
_E5_VOYAGE = re.compile(r"\bV\d{3}\b")
_E5_CP = re.compile(r"\bCPDD\s*\d{1,2}[A-Z]{3}\d{4}\b", re.I)
_E5_TONS = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?MT\b", re.I)
# Whole-word cues before a tonnage; the nearest one wins (review 2026-09-26: "problem" is not
# ROB, and in "Loaded 50 MT, ROB 20 MT" the 20 MT is ROB).
_E5_TON_CUE = re.compile(r"\b(discharg\w*|load(?:ed|ing)|rob|bunkers?)\b", re.I)
_E5_TON_WINDOW = 30  # characters looked back, never past the previous tonnage
E5_ATTEMPTS = 2  # one retry (E5-S03)
_E5_UNIT_GROUPS = (
    {"mt", "mts", "ton", "tons", "tonne", "tonnes", "t", "metric ton", "metric tons"},
    {"kn", "kt", "kts", "knot", "knots"},
    {"%", "pct", "percent"},
    {"h", "hr", "hrs", "hour", "hours"},
    {"usd", "us$", "$"},
    {"eur", "€"},
    {"cny", "rmb", "¥"},
)
_E5_CURRENCY_SIGNS = {"USD": ("usd", "us$", "$"), "EUR": ("eur", "€"), "CNY": ("cny", "rmb", "¥")}


def _ton_kind(cue: str) -> str:
    cue = cue.lower()
    if cue.startswith("discharg"):
        return "discharged"
    if cue.startswith("load"):
        return "loaded"
    return "bunker_rob"


def _norm(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _grounded_text(value: str, quote: str) -> bool:
    """A returned name or reference must be written in its own quote (review 2026-09-26)."""
    return bool(_norm(value)) and _norm(value) in _norm(quote)


def _grounded_quantity(q: QuantityFact) -> bool:
    """The number and the currency must be in the quote. The unit may come from context (a
    table header, "[BROB_VLSFO : 339.11]"), like a date's day; it is rejected only when the
    quote names a different unit. Dates are not checked here (a normalised date may add
    context that the quote does not repeat)."""
    quote = _norm(q.evidence.quote)
    numbers = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", quote)}
    if not any(abs(n - q.value) < 1e-9 for n in numbers):
        return False
    if q.currency:
        signs = _E5_CURRENCY_SIGNS.get(q.currency.upper(), (q.currency.casefold(),))
        if not any(sign in quote for sign in signs):
            return False
    unit = _norm(q.unit)
    group = next((g for g in _E5_UNIT_GROUPS if unit in g), {unit})
    named = [
        g
        for g in _E5_UNIT_GROUPS
        if any(re.search(rf"(?<![a-z]){re.escape(u)}(?![a-z])", quote) for u in g)
    ]
    return not named or group in named


def _locate(quote: str, email: ParsedEmail) -> Evidence | None:
    """Evidence for a quote that really appears in the email, else None (the item is dropped).
    Case, spacing and straight or curly quotation marks do not count as a difference; an
    ellipsis or any other change of words does (T2.8: E060, E063 were lost on "owner’s")."""
    if not isinstance(quote, str) or not quote.strip():
        return None
    key = _quote_key(quote)
    if key in _quote_key(email.new_text):
        return Evidence(quote=quote, source="new_text")
    if key in _quote_key(email.subject):
        return Evidence(quote=quote, source="subject")
    if any(key in _quote_key(name) for name in email.attachment_names):
        return Evidence(quote=quote, source="attachments")
    return None


_QUOTE_MARKS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _quote_key(text: str) -> str:
    return " ".join(text.translate(_QUOTE_MARKS).casefold().split())


def _e5_rules(email: ParsedEmail) -> ExtractedEntities:
    """Regex pre-pass: vessel codes, voyage numbers, CP dates, tonnages (text first, then subject)."""
    out = ExtractedEntities(llm_status="skipped")
    for source, text in (("new_text", email.new_text), ("subject", email.subject)):
        for pattern, target in ((_E5_VESSEL, out.vessel_mentions), (_E5_VOYAGE, out.voyage_numbers),
                                (_E5_CP, out.cp_references)):  # fmt: skip
            for m in pattern.finditer(text):
                # vessel mentions are kept once per source: D1 weighs subject and text apart
                seen = [
                    (x.text, x.evidence.source) if target is out.vessel_mentions else x.text
                    for x in target
                ]
                key = (m.group(0), source) if target is out.vessel_mentions else m.group(0)
                if key not in seen:
                    target.append(
                        Mention(text=m.group(0), evidence=Evidence(quote=m.group(0), source=source))
                    )
        previous_end = 0
        for m in _E5_TONS.finditer(text):
            window = text[max(previous_end, m.start() - _E5_TON_WINDOW) : m.start()]
            cues = list(_E5_TON_CUE.finditer(window))
            kind = _ton_kind(cues[-1].group(1)) if cues else "other"
            previous_end = m.end()
            value = float(m.group(1).replace(",", ""))
            out.quantities.append(
                QuantityFact(
                    kind=kind,
                    value=value,
                    unit="MT",
                    evidence=Evidence(quote=m.group(0), source=source),
                )
            )
    return out


def _e5_merge(out: ExtractedEntities, answer: dict, email: ParsedEmail) -> None:
    """Add the LLM's items that pass the contract; anything else is dropped, never repaired."""

    def items(name: str) -> list[dict]:
        value = answer.get(name)
        return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []

    def build(make, item, grounded=lambda built: True):
        evidence = _locate(item.get("quote"), email)
        if evidence is None:
            return None
        try:
            built = make(item, evidence)
        except (ValidationError, TypeError, ValueError, KeyError):
            return None  # a malformed item is dropped, never repaired
        return built if grounded(built) else None

    def mention(i, ev):
        return Mention(text=str(i.get("text") or i["quote"]), evidence=ev)

    def mention_grounded(m):
        return _grounded_text(m.text, m.evidence.quote)

    for name in ("vessel_mentions", "voyage_numbers", "ports", "cp_references"):
        target = getattr(out, name)
        for item in items(name):
            m = build(mention, item, mention_grounded)
            if name == "vessel_mentions":
                seen = [(x.text, x.evidence.source) for x in target]
                if m and (m.text, m.evidence.source) not in seen:
                    target.append(m)
            elif m and m.text not in [x.text for x in target]:
                target.append(m)
    for item in items("dates"):
        d = build(
            lambda i, ev: DateFact(
                kind=i["kind"], value=str(i["value"]), ordinal=i.get("ordinal"), evidence=ev
            ),
            item,
        )
        if d and (d.kind, d.value) not in [(x.kind, x.value) for x in out.dates]:
            out.dates.append(d)
    for item in items("quantities"):
        q = build(lambda i, ev: QuantityFact(kind=i["kind"], value=i["value"], unit=str(i["unit"]),
                                             currency=i.get("currency"), evidence=ev), item, _grounded_quantity)  # fmt: skip
        if q is None:
            continue
        same = [
            x for x in out.quantities if x.value == q.value and x.unit.lower() == q.unit.lower()
        ]
        for x in same:
            if x.kind == "other" or x.kind == q.kind:
                out.quantities.remove(x)  # the LLM names the kind of a tonnage the rule found
        out.quantities.append(q)
    for item in items("references"):
        r = build(
            lambda i, ev: Reference(kind=i["kind"], value=str(i["value"]), evidence=ev),
            item,
            lambda ref: _grounded_text(ref.value, ref.evidence.quote),
        )
        if r and (r.kind, r.value) not in [(x.kind, x.value) for x in out.references]:
            out.references.append(r)
    hint = answer.get("author_hint")
    if isinstance(hint, dict):
        out.author_hint = build(mention, hint, mention_grounded)


def _e5_subject_conflict(out: ExtractedEntities) -> None:
    """Subject and text give different values for one kind: keep the text value (E5-S13)."""
    for kind in {q.kind for q in out.quantities}:
        text_values = {
            q.value for q in out.quantities if q.kind == kind and q.evidence.source == "new_text"
        }
        subject = [q for q in out.quantities if q.kind == kind and q.evidence.source == "subject"]
        clash = [q for q in subject if text_values and q.value not in text_values]
        if clash:
            out.subject_text_conflict = True
            out.quantities = [q for q in out.quantities if q not in clash]


def e5_extract_entities(
    email: ParsedEmail, roles: PartyRoles, check: SanitizationCheck, llm: LlmClient
) -> ExtractedEntities:
    """E5 Extract (design_backend.md E5 row, prompts.md section 3): regex pre-pass, then the LLM
    for the rest. Only a clean email reaches the LLM (E4 is the data boundary)."""
    if check.status != "clean":
        return ExtractedEntities(llm_status="skipped")
    out = _e5_rules(email)
    found = [m.text for m in out.vessel_mentions + out.voyage_numbers + out.cp_references]
    found += [q.evidence.quote for q in out.quantities]
    user = prompts.e5_user(
        email.subject, email.new_text, email.attachment_names, email.direction, roles.sender.role,
        email.sent_time.isoformat() if email.sent_time else None, found,
    )  # fmt: skip
    answer = None
    for _ in range(E5_ATTEMPTS):
        try:
            answer = llm.complete_json("E5", email.email_id, prompts.E5_SYSTEM, user)
        except LlmError:
            continue
        if isinstance(answer, dict):
            break
        answer = None  # not a JSON object: no usable answer, like a failed call (LlmStatus)
    if answer is None:
        return out.model_copy(update={"llm_status": "failed"})
    _e5_merge(out, answer, email)
    _e5_subject_conflict(out)
    return out.model_copy(update={"llm_status": "ok"})


# --- E6 e6_detect_event -----------------------------------------------------------

REPORT_EVENT = "Vessel Report (Noon / Arrival / Berthing / Sailing / Daily)"
FYI_EVENT = "General / FYI"
# Report titles (the taxonomy's report type and the titles of the corpus) and the Chinese terms
# (F12) [AMENDMENT 2026-09-26 T2.8]. "PSC inspection report" or "berth report" are not titles.
_REPORT_KEYWORD = re.compile(
    r"\b(?:noon|daily|arrival|berthing|sailing|departure|cosp|eosp)\s+report\b|\beta notice\b"
    r"|午报|日报|抵港报|离港报|靠泊报",
    re.I,
)
# The content pattern of a report: at least one report field in the new text
_REPORT_FIELD = re.compile(
    r"\bposition\b|\d{1,3}-\d{2}(?:\.\d+)?\s?[NSEW]\b|\bspeed\b|\bknots?\b|\bkts\b|\brob\b"
    r"|\bbunkers?\b|\bvlsfo\b|\blsmgo\b|\beta\b|\betb\b|\betd\b|\bweather\b|\bwind\b|\bswell\b"
    r"|\bdistance\b|\bdtg\b|\[[A-Za-z_]+ ?: ",
    re.I,
)
E6_ATTEMPTS = 2  # one retry
E6_RULE_CONFIDENCE = 0.9
E6_MAX_ITEMS = 3


def _e6_fallback(llm_status: str) -> EventCandidates:
    """ "General / FYI" at confidence 0; D3 marks it unsure (E6-S04, S05)."""
    evidence = Evidence(quote="no event type detected", source="kb")
    item = EventCandidate(event_type=FYI_EVENT, confidence=0.0, source="llm", evidence=evidence)
    return EventCandidates(items=[item], is_report=False, llm_status=llm_status)


def e6_detect_event(
    email: ParsedEmail,
    entities: ExtractedEntities,
    voyage: VoyageMatch,
    roles: PartyRoles,
    taxonomy: dict[str, list[str]],
    llm: LlmClient,
) -> EventCandidates:
    """E6 Detect (design_backend.md E6 row, prompts.md section 4): the report rule first
    (inbound, a report title in the subject, a report field in the text), the LLM for the rest.
    The LLM only proposes; D3 decides."""
    keyword = _REPORT_KEYWORD.search(email.subject)
    if keyword and email.direction == "Inbound" and _REPORT_FIELD.search(email.new_text):
        evidence = Evidence(quote=keyword.group(0), source="subject")
        item = EventCandidate(
            event_type=REPORT_EVENT, confidence=E6_RULE_CONFIDENCE, source="rule", evidence=evidence
        )
        return EventCandidates(items=[item], is_report=True, llm_status="skipped")

    known = list(taxonomy.get("event_types", []))
    summary = {
        "vessel_mentions": [m.text for m in entities.vessel_mentions],
        "voyage_numbers": [m.text for m in entities.voyage_numbers]
        or ([voyage.voyage_no] if voyage.voyage_no else []),
        "ports": [m.text for m in entities.ports],
        "date_kinds": sorted({d.kind for d in entities.dates}),
    }
    user = prompts.e6_user(
        email.subject, email.new_text, summary, email.direction, roles.sender.role, known
    )
    answer = None
    for _ in range(E6_ATTEMPTS):
        try:
            answer = llm.complete_json("E6", email.email_id, prompts.E6_SYSTEM, user)
        except LlmError:
            continue
        if isinstance(answer, dict):
            break
        answer = None  # not a JSON object: no usable answer
    if answer is None:
        return _e6_fallback("failed")

    items: list[EventCandidate] = []
    raw = answer.get("items")
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or item.get("event_type") not in known:
            continue  # outside the taxonomy: rejected (E6-S04)
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            continue
        located = _locate(quote, email)
        if located is None or located.source == "attachments":
            continue  # the quote is not in the subject or the text
        source = located.source
        try:
            candidate = EventCandidate(event_type=item["event_type"], confidence=item["confidence"],
                                       source="llm", evidence=Evidence(quote=quote, source=source))  # fmt: skip
        except (ValidationError, KeyError, TypeError):
            continue
        if candidate.event_type not in [c.event_type for c in items]:
            items.append(candidate)
    items = sorted(items, key=lambda c: -c.confidence)[:E6_MAX_ITEMS]
    if not items:
        return _e6_fallback("ok")
    return EventCandidates(items=items, is_report=False, llm_status="ok")


# --- E6b e6b_derive_fact_changes ---------------------------------------------------

# Fact keys of design_knowledge section 2 [AMENDMENT 2026-09-26 T2.11: port and grade rules]
_PORT_KEYED = {"eta", "etb", "etd", "arrived", "berthed", "commenced", "completed", "sailed"}
_ACTUAL_KINDS = {"arrived", "berthed", "commenced", "completed", "sailed", "nor_tendered"}
_GRADES = re.compile(r"\b(VLSFO|ULSFO|HSFO|LSFO|VLSDGO|ULSDGO|HSDGO|LSMGO|MGO|MDO|FW)\b", re.I)
_EFFECTIVE = re.compile(
    r"\b(?:as of|effective(?: from)?|w\.?e\.?f\.?)\s+(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):?(\d{2})",
    re.I,
)
_VALUE_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):?(\d{2})")
_SOURCE_RANK = {"new_text": 0, "subject": 1, "attachments": 2, "quoted_text": 3, "kb": 4}


def _key_part(text: str) -> str:
    return "_".join(re.sub(r"[^\w]+", " ", text.casefold()).split()) or "unknown"


def _fact_port(quote: str, entities: ExtractedEntities) -> str:
    """The port written in the fact's own quote; else the only port the email names; else unknown."""
    named = [p.text for p in entities.ports]
    inside = [p for p in named if p.casefold() in quote.casefold()]
    if inside:
        return _key_part(inside[0])
    distinct = {_key_part(p) for p in named}
    return distinct.pop() if len(distinct) == 1 else "unknown"


def _time_in(pattern: re.Pattern, text: str, zone) -> datetime | None:
    m = pattern.search(text)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()), tzinfo=zone)
    except ValueError:
        return None


def _current(key: str, lookup: FactLookup) -> FactRecord | None:
    """The current value is derived, never stored (design_backend 11.A)."""
    active = [f for f in lookup.facts if f.fact_key == key and f.state == "active"]
    if not active:
        return None
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return max(active, key=lambda f: (f.event_time, f.sent_time or floor, f.source_email_id))


def e6b_derive_fact_changes(
    entities: ExtractedEntities,
    vessel: VesselMatch,
    voyage: VoyageMatch,
    event: EventDecision,
    email: ParsedEmail,
    lookup: FactLookup,
) -> FactChanges:
    """E6b Transform (design_backend.md E6b row, design_knowledge section 2): extracted values to
    fact changes against the current facts. No vessel, or an unavailable lookup, gives none
    (the pipeline holds the email; unavailable is never read as "no facts")."""
    if vessel.status != "matched" or lookup.status != "ok":
        return FactChanges()
    zone = email.sent_time.tzinfo if email.sent_time else timezone.utc
    trip = voyage.voyage_no or "unknown"
    found: list[tuple[str, str, Evidence, datetime | None, str | None]] = []

    for d in entities.dates:
        quote = d.evidence.quote
        if d.kind in _PORT_KEYED:
            key = f"{d.kind}:{_fact_port(quote, entities)}"
        elif d.kind == "nor_tendered":
            key = f"nor:{_fact_port(quote, entities)}:{d.ordinal or 1}"
        elif d.kind == "laycan":
            key = f"laycan:{trip}"
        elif d.kind in ("delivery", "redelivery"):
            key = f"{d.kind}_time:{trip}"
        else:
            continue  # deadline and other are not vessel facts
        stated = (
            _time_in(_VALUE_TIME, d.value, zone)
            if d.kind in _ACTUAL_KINDS
            else _time_in(_EFFECTIVE, quote, zone)
        )
        found.append((key, d.value, d.evidence, stated, "stated" if stated else None))

    for q in entities.quantities:
        quote = q.evidence.quote
        grade = _GRADES.search(quote)
        grade = grade.group(1).lower() if grade else "unknown"
        if q.kind in ("loaded", "discharged"):
            key = f"cargo_{q.kind}_mt:{_fact_port(quote, entities)}"
        elif q.kind == "bunker_rob":
            key = f"bunker_rob:{grade}"
        elif q.kind == "speed":
            key = "speed_avg"
        elif q.kind == "consumption":
            key = f"consumption:{grade}"
        elif q.kind == "amount":
            refs = [r.value for r in entities.references if r.kind == "invoice"]
            key = f"invoice_amount:{refs[0] if refs else 'unknown'}"
        else:
            continue
        value = f"{q.value:g} {q.currency if q.kind == 'amount' and q.currency else q.unit}"
        found.append((key, value, q.evidence, None, None))

    chosen: dict[str, tuple] = {}
    for item in found:  # one change per key: the text before the subject, then the first
        key = item[0]
        if key not in chosen or _SOURCE_RANK[item[2].source] < _SOURCE_RANK[chosen[key][2].source]:
            chosen[key] = item
    order = list(dict.fromkeys(item[0] for item in found))

    changes = []
    for key in order:
        _, value, evidence, stated, basis = chosen[key]
        event_time = stated or email.sent_time
        basis = basis or ("email_sent_time" if email.sent_time else None)
        current = _current(key, lookup)
        if current and current.value == value:
            continue  # E6b-S03
        changes.append(FactChange(
            fact_key=key, old=current.value if current else None, new=value, event_time=event_time,
            event_time_basis=basis, evidence=evidence, base_version=current.version if current else None,
            older_than_current=bool(current and event_time and event_time < current.event_time),
        ))  # fmt: skip
    return FactChanges(items=changes)


# --- E7 e7_generate_actions --------------------------------------------------------

NO_ACTION = "No Action"
E7_ATTEMPTS = 2  # one retry
E7_MAX_ITEMS = 5
DEFAULT_OWNER = "Operator (internal)"


def _allowed_actions(event: EventDecision, action_rules: dict) -> dict[str, list[str]]:
    """Action types allowed per event: the rows of the primary and the secondary events (F9);
    "No Action" is not an action."""
    allowed: dict[str, list[str]] = {}
    for event_type in [event.event_type, *event.secondary_event_types]:
        rule = action_rules.get(event_type)
        types = [t for t in (rule.default_action_types if rule else []) if t != NO_ACTION]
        if types:
            allowed[event_type] = types
    return allowed


def _candidate(
    action_type, for_event, description, due, owner, templated, action_rules
) -> ActionCandidate:
    """The rule parts come from the row (⬜): decision basis and due type (U1); Others takes
    the action type as its short text."""
    rule = action_rules[for_event]
    due_type = rule.default_due_type or "Others"
    return ActionCandidate(
        action_type=action_type, description=description, due=due, due_type=due_type,
        due_other=action_type if due_type == "Others" else None, owner_role=owner or DEFAULT_OWNER,
        decision_basis=rule.decision_basis or "", templated=templated, for_event=for_event,
    )  # fmt: skip


def e7_generate_actions(
    event: EventDecision,
    entities: ExtractedEntities,
    voyage: VoyageMatch,
    email: ParsedEmail,
    action_rules: dict,
    now: datetime,
    llm: LlmClient,
) -> ActionCandidates:
    """E7 Generate (design_backend.md E7 row, prompts.md section 5): action types come from the
    rule rows; the LLM only words each action and reads its date. No allowed type (no row, a
    report, FYI) makes no call. A failed call gives the row's template text."""
    allowed = _allowed_actions(event, action_rules)
    if event.is_report or not allowed:
        return ActionCandidates(items=[], llm_status="skipped")
    summary = {
        "vessel_mentions": [m.text for m in entities.vessel_mentions],
        "ports": [m.text for m in entities.ports],
        "dates": [[d.kind, d.value] for d in entities.dates],
    }
    user = prompts.e7_user(event.event_type, event.secondary_event_types, allowed, summary,
                           None, voyage.voyage_no, email.new_text, now.date().isoformat())  # fmt: skip
    answer = None
    for _ in range(E7_ATTEMPTS):
        try:
            answer = llm.complete_json("E7", email.email_id, prompts.E7_SYSTEM, user)
        except LlmError:
            continue
        if isinstance(answer, dict):
            break
        answer = None
    if answer is None:
        templates = [
            _candidate(t, ev, f"{t}: {ev}", None, None, True, action_rules)
            for ev, types in allowed.items() for t in types
        ][:E7_MAX_ITEMS]  # fmt: skip
        return ActionCandidates(items=templates, llm_status="failed")

    items: list[ActionCandidate] = []
    raw = answer.get("items")
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        action_type = item.get("action_type")
        owners = [ev for ev, types in allowed.items() if action_type in types]
        if not owners:
            continue  # not allowed for the event (E7-S02)
        for_event = item.get("for_event") if item.get("for_event") in owners else owners[0]
        due = item.get("due")
        try:
            due = date.fromisoformat(due) if due else None
            description = item["description"]
            if not isinstance(description, str) or not description.strip():
                continue
            items.append(_candidate(action_type, for_event, description.strip(), due,
                                    item.get("owner_role"), False, action_rules))  # fmt: skip
        except (ValidationError, ValueError, TypeError, KeyError):
            continue  # a long text, a date that cannot be read or a missing key: dropped
        if len(items) == E7_MAX_ITEMS:
            break
    return ActionCandidates(items=items, llm_status="ok")


# --- E9 e9_route_by_policy ---------------------------------------------------------

# design_knowledge section 3 (policy.yaml); moved to a file in T4.4
NEVER_AUTO_EVENTS = {
    "Claim", "LOI (Letter of Indemnity)", "Off-hire", "Vessel Defect / Repair / Breakdown",
    "Sanctions / Compliance / KYC", "CP Terms / Recap / Addendum",
}  # fmt: skip


def e9_route_by_policy(
    event: EventDecision,
    vessel: VesselMatch,
    task: TaskDisposition,
    facts: FactChanges,
    email: ParsedEmail,
) -> Lane:
    """E9 Select (design_backend.md E9 row, design_knowledge section 3): automatic only for a
    report on a High vessel with no conflict, a time on every fact and nothing in never_auto;
    every other case, and any unknown case, needs the officer [AMENDMENT 2026-09-26 T2.16: args add
    FactChanges and ParsedEmail]."""
    reasons = []
    if not event.is_report:
        reasons.append("non_report_event")
    if event.unsure:
        reasons.append("event_unsure")
    if vessel.status != "matched" or vessel.tier != "High":
        reasons.append("vessel_not_high")
    if any(f.older_than_current for f in facts.items):
        reasons.append("conflicts_with_newer_fact")
    if any(f.event_time is None for f in facts.items):
        reasons.append("fact_without_time")
    if event.event_type in NEVER_AUTO_EVENTS:
        reasons.append("never_auto_event")
    if email.attachment_dependent:
        reasons.append("attachment_dependent")
    if task.kind != "none":
        reasons.append("task_change")
    return Lane(lane="needs_confirm" if reasons else "auto_apply", reasons=reasons)


# --- E10 e10_build_proposal --------------------------------------------------------


def e10_build_proposal(
    proposal_id: str,
    email: ParsedEmail,
    vessel: VesselMatch | None,
    voyage: VoyageMatch | None,
    event: EventDecision | None,
    needs: NeedsActionDecision | None,
    facts: FactChanges | None,
    actions: RankedActions | None,
    task: TaskDisposition | None,
    lane: Lane,
) -> Proposal:
    """E10 Transform: assemble what the officer sees, with one trace step per decision. A
    missing upstream result makes the proposal incomplete and forces needs_confirm (E10-S02).
    The statuses are [Close] only for a close proposal; otherwise D4's plus the action marks."""
    incomplete = any(x is None for x in (vessel, voyage, event, needs, actions, task))
    vessel = vessel or VesselMatch(
        vessel_code=None, status="none", tier="Low", score=0.0, rule_triggered="missing"
    )
    voyage = voyage or VoyageMatch(voyage_no=None, basis="none", rule_triggered="missing")
    event = event or EventDecision(event_type=FYI_EVENT, tier="Low", unsure=True, is_report=False, sources_agree=True,
                                   rule_triggered="missing")  # fmt: skip
    actions = actions or RankedActions(rule_triggered="missing")
    task = task or TaskDisposition(kind="none", rule_triggered="missing")
    if needs is None:
        needs = NeedsActionDecision(
            statuses=["Action Required"], priority=3, reason="missing", rule_triggered="missing"
        )
    if incomplete:
        lane = Lane(lane="needs_confirm", reasons=[*lane.reasons, "incomplete"])
    statuses = (
        ["Close"] if task.kind == "close_proposal" else d_nodes.suggested_statuses(needs, actions)
    )
    priority = max((a.priority for a in actions.items), default=needs.priority)

    def step(node, obj, confidence=None, evidence=()):
        return TraceStep(node=node, rule_or_basis=f"{obj.rule_triggered}: {obj.reason}", confidence=confidence,
                         evidence=list(evidence))  # fmt: skip

    trace = [
        step("D1", vessel, vessel.score, vessel.evidence),
        step("D2", voyage, None, voyage.evidence),
        step("D3", event),
        step("D4", needs),
        step("D5", actions),
        step("D6", task),
        TraceStep(node="E9", rule_or_basis=f"{lane.lane}: {', '.join(lane.reasons) or 'policy'}"),
    ]
    return Proposal(proposal_id=proposal_id, email_id=email.email_id, lane=lane, vessel=vessel, voyage=voyage,
                    event=event, statuses=statuses, priority=priority, fact_changes=(facts or FactChanges()).items,
                    task=task, actions=actions, trace=trace, incomplete=incomplete)  # fmt: skip


# --- E10b e10b_save_proposal -------------------------------------------------------


def e10b_save_proposal(
    item: Proposal | HeldRecord, email: ParsedEmail | None, thread_id: str | None, store: Store
) -> SavedProposal:
    """E10b eXecute: the email row and its proposal (or held record) in one transaction. A write
    failure is a hard failure (E10b-S04); nothing is lost silently."""
    with store.transaction() as tx:
        if email is not None:
            tx.save_email(email, thread_id)
        if isinstance(item, HeldRecord):
            return tx.save_held(item)
        return tx.save_proposal(item)


# --- E17 e17_get_email, E18 e18_search_emails [AMENDMENT 2026-09-28, read-only tools] --------

from src.schemas import (  # noqa: E402
    ChatAnswer,
    ChatContext,
    ChatEmail,
    ChatRequest,
    GetEmailArgs,
    SearchEmailsArgs,
    SourceRef,
    ToolCallLog,
)

_SEARCH_LIMIT_CAP = 20


def chat_email_view(email: ParsedEmail, kb: KnowledgeBase) -> ChatEmail | None:
    """A short view of a stored email; never one that fails the E4 check. Shared by
    build_chat_context (api.py) and E17/E18, so every chat-facing email view agrees."""
    if e4_check_sanitized(email).status != "clean":
        return None
    who = e3_resolve_sender(email, kb).sender
    sender = "us" if email.direction == "Outbound" else " ".join(x for x in (who.role, who.party_code) if x)
    excerpt = " ".join(email.new_text.split())[:500]
    return ChatEmail(email_id=email.email_id, subject=email.subject, sent_time=email.sent_time,
                     sender=sender, excerpt=excerpt)  # fmt: skip


def e17_get_email(email_id: str, store: Store, kb: KnowledgeBase) -> ChatEmail | None:
    """E17 Select (design_backend.md E17 row): any email in the store by id, not only the ~40
    already in ChatContext (E17-S01 to S03). An id that does not exist, or whose email fails
    E4, is not a match; the model is told "not found", never given a guess."""
    email = store.get_email(email_id)
    return chat_email_view(email, kb) if email else None


def e18_search_emails(
    vessel: str | None, event_type: str | None, status: str | None, limit: int, store: Store, kb: KnowledgeBase
) -> list[ChatEmail]:  # fmt: skip
    """E18 Select (design_backend.md E18 row): filter the store's emails, via the proposal each
    one produced, by vessel, event type or status (E18-S01, S02); E4-clean only, newest first;
    capped at 20 in code regardless of the limit asked for (E18-S04). At least one filter is
    required — SearchEmailsArgs rejects a call with none (E18-S03) before this runs."""
    matched = [
        r for r in store.proposal_rows(("applied",))
        if r["proposal"] is not None
        and (not vessel or r["proposal"].vessel.vessel_code == vessel)
        and (not event_type or r["proposal"].event.event_type == event_type)
        and (not status or status in r["proposal"].statuses)
    ]  # fmt: skip
    floor = datetime.min.replace(tzinfo=timezone.utc)
    matched.sort(key=lambda r: r["sent_time"] or floor, reverse=True)
    out: list[ChatEmail] = []
    for r in matched:
        if len(out) >= min(limit, _SEARCH_LIMIT_CAP):
            break
        email = store.get_email(r["email_id"])
        view = chat_email_view(email, kb) if email else None
        if view:
            out.append(view)
    return out


_TOOL_ARGS = {"get_email": GetEmailArgs, "search_emails": SearchEmailsArgs}
TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_email",
        "description": "Look up one email anywhere in the store by id, not only the ones already given.",
        "parameters": {"type": "object", "properties": {"email_id": {"type": "string"}},
                       "required": ["email_id"]},
    }},  # fmt: skip
    {"type": "function", "function": {
        "name": "search_emails",
        "description": "Search the store's emails by vessel, event type or status; at least one filter is required.",
        "parameters": {"type": "object", "properties": {
            "vessel": {"type": "string"}, "event_type": {"type": "string"},
            "status": {"type": "string"}, "limit": {"type": "integer"}}},
    }},  # fmt: skip
]


def _summarize_tool_result(value: ChatEmail | list[ChatEmail] | None) -> str:
    if value is None:
        return "not found"
    if isinstance(value, list):
        return "no matches" if not value else f"{len(value)} email" + ("" if len(value) == 1 else "s")
    return "1 email"


def _execute_tool_calls(
    calls: list[dict], run_tool: Callable[[str, dict], ChatEmail | list[ChatEmail] | None], budget: int
) -> tuple[list[dict], list[ToolCallLog], list[ChatEmail]]:
    """Runs (or refuses) the tool calls of one model turn. `budget` is how many more real calls
    MAX_TOOL_CALLS still allows for this whole exchange; a call past it gets an error result but
    never reaches `run_tool`, so the cap holds even if one turn asks for several calls at once."""
    results: list[dict] = []
    logs: list[ToolCallLog] = []
    seen: list[ChatEmail] = []
    for i, call in enumerate(calls):
        name, raw_args = call.get("name"), call.get("arguments") or {}
        args_model = _TOOL_ARGS.get(name)
        if args_model is None:
            results.append({"name": name, "arguments": raw_args, "error": f"unknown tool {name!r}"})
            continue
        if i >= budget:
            results.append({"name": name, "arguments": raw_args, "error": "tool call cap reached"})
            logs.append(ToolCallLog(name=name, arguments=raw_args, result_summary="cap reached"))
            continue
        try:
            clean_args = args_model.model_validate(raw_args).model_dump(exclude_none=True)
        except ValidationError as exc:
            err = exc.errors()[0]["msg"]
            results.append({"name": name, "arguments": raw_args, "error": err})
            logs.append(ToolCallLog(name=name, arguments=raw_args, result_summary=f"error: {err}"))
            continue
        try:
            value = run_tool(name, clean_args)
        except Exception as exc:  # noqa: BLE001 - a broken tool fails closed, not a crash
            err = type(exc).__name__
            results.append({"name": name, "arguments": clean_args, "error": err})
            logs.append(ToolCallLog(name=name, arguments=clean_args, result_summary=f"error: {err}"))
            continue
        dumped = (
            value.model_dump(mode="json") if hasattr(value, "model_dump")
            else [v.model_dump(mode="json") for v in value] if isinstance(value, list)
            else None
        )  # fmt: skip
        results.append({"name": name, "arguments": clean_args, "result": dumped})
        logs.append(ToolCallLog(name=name, arguments=clean_args, result_summary=_summarize_tool_result(value)))
        seen.extend(value if isinstance(value, list) else [value] if value is not None else [])
    return results, logs, seen


def _run_tool_loop(
    llm: LlmClient, key: str, system: str, user: str,
    run_tool: Callable[[str, dict], ChatEmail | list[ChatEmail] | None],
) -> tuple[dict, list[ToolCallLog], list[ChatEmail], bool]:
    """Drives E16's tool loop to a final answer (design_backend.md 9.4). Offers TOOL_SPECS until
    MAX_TOOL_CALLS real calls have run in this exchange; past the cap no `tools` are offered, so
    a further call is structurally impossible, not merely discouraged. The fourth return value
    is whether the final answer was produced with no tools left to offer (protocol/chordx_agent.md
    §8's RETRIEVAL_LIMIT_REACHED is code-decidable exactly from this, not from the model's say-so)."""
    turns: list[dict] = []
    logs: list[ToolCallLog] = []
    seen: list[ChatEmail] = []
    used = 0
    cap_reached = False
    for _ in range(MAX_TOOL_CALLS + 2):  # generous bound: MAX_TOOL_CALLS rounds, plus one forced-final
        cap_reached = used >= MAX_TOOL_CALLS
        tools = [] if cap_reached else TOOL_SPECS
        step = llm.complete_chat("E16", key, system, user, tools, turns)
        if "final" in step:
            return step["final"], logs, seen, cap_reached
        calls = step.get("tool_calls") or []
        if not calls:
            raise LlmError(f"E16 turn for {key} had neither tool_calls nor final")
        results, new_logs, new_seen = _execute_tool_calls(calls, run_tool, MAX_TOOL_CALLS - used)
        logs.extend(new_logs)
        seen.extend(new_seen)
        used += len(calls)
        turns.append({"tool_calls": calls})
        turns.append({"tool_results": results})
    raise LlmError(f"E16 tool loop for {key} did not reach a final answer")


# --- E16 e16_answer_chat [AMENDMENT 2026-09-26 U3] [AMENDMENT 2026-09-28, read-only tools] ---

CHAT_FAILED = "I cannot answer that now; the pages still show everything."
_CHAT_REVIEW = re.compile(r"\breview\b|\bnew e-?mails?\b", re.I)
_CHAT_PAGES = {"email": "Email page", "overview": "Overview", "vessel": "Vessel page", "action": "Action page"}
MAX_TOOL_CALLS = 3  # [AMENDMENT 2026-09-28] enforced by the loop counter above, not a prompt rule


def chat_key(question: str) -> str:
    """Recording key of a chat answer: the normalised question (E16-S08)."""
    import hashlib  # noqa: PLC0415

    norm = " ".join(question.lower().split()).rstrip("?!. ")
    return "q-" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _chat_ids(context: ChatContext) -> dict[str, dict[str, str]]:
    """Every id the answer may cite, with a default label, per kind."""
    emails = {e.email_id: e.subject for e in context.emails}
    tasks: dict[str, str] = {}
    for group in context.tasks.groups:
        for row in group.items:
            tasks[row.task_id] = row.action
            emails.setdefault(row.source_email_id, row.source_email_id)
    for item in context.review_queue.items:
        emails.setdefault(item.email_id, item.email_id)
    for view in context.vessels:
        for f in view.facts:
            emails.setdefault(f.source_email_id, f.source_email_id)
        for t in view.timeline:
            emails.setdefault(t.email_id, t.email_id)
    vessels = {v.vessel_code: v.vessel_code for v in context.vessels}
    return {"email": emails, "task": tasks, "vessel": vessels, "page": dict(_CHAT_PAGES)}


def _chat_context_json(context: ChatContext) -> dict:
    """The context as the model sees it: codes only, current facts, no audit internals."""
    tasks = {}
    for group in context.tasks.groups:
        for row in group.items:
            tasks[row.task_id] = {
                "task_id": row.task_id, "vessel": row.vessel, "voyage": row.voyage, "title": row.action,
                "statuses": row.statuses, "priority": row.priority, "overdue": row.overdue,
                "source_email_id": row.source_email_id,
                "actions": [{"text": a.description, "priority": a.priority, "due": a.due_date,
                             "due_type": a.due_type if a.due_type != "Others" else f"Others: {a.due_other}",
                             "needs_approval": a.needs_approval, "awaiting_reply": a.awaiting_reply}
                            for a in row.actions],
            }  # fmt: skip
    open_tasks = list(tasks.values())
    review_queue = [i.model_dump(mode="json") for i in context.review_queue.items]
    return {
        # [AMENDMENT 2026-09-28, fourth live-demo finding] the model was asked to count these
        # arrays itself and got it wrong (it read "5 items" as "5 total" even at temperature=0);
        # counting a list's length is exact arithmetic, not wording, so it is done here, in code,
        # not left to the model. Both arrays are already in priority order (D7, E14), so "the
        # first five" is a mechanical read, not a ranking judgment; only the total was unreliable.
        "open_tasks_total": len(open_tasks),
        "open_tasks": open_tasks,
        "dues": [d.model_dump(mode="json") for d in context.dues.items],
        "vessels": [
            {"vessel": v.vessel_code,
             "current_facts": [{"fact": f.fact_key, "value": f.value, "time": f.event_time.isoformat(),
                                "email_id": f.source_email_id} for f in v.facts if not f.superseded],
             "recent_events": [{"time": t.event_time.isoformat(), "event": t.event_type, "email_id": t.email_id}
                               for t in v.timeline[-8:]]}
            for v in context.vessels
        ],
        "review_queue_total": len(review_queue),
        "review_queue": review_queue,
        "emails": [e.model_dump(mode="json") for e in context.emails],
    }  # fmt: skip


def _review_answer(context: ChatContext) -> ChatAnswer:
    """E16-S04, S05: the card is the first open item of E14's queue, chosen by rule."""
    first = next((i for i in context.review_queue.items if i.status == "open"), None)
    if first is None:
        return ChatAnswer(text="Nothing is waiting for your review.", llm_status="skipped",
                          sources=[SourceRef(kind="page", id="email", label="Email page")])  # fmt: skip
    subject = next((e.subject for e in context.emails if e.email_id == first.email_id), first.email_id)
    waiting = sum(1 for i in context.review_queue.items if i.status == "open")
    where = " · ".join(x for x in (first.vessel, first.event_type) if x)
    text = f"New email to review: {subject}" + (f" ({where})." if where else ".")
    if waiting > 1:
        text += f" {waiting - 1} more are waiting on the Email page."
    sources = [SourceRef(kind="email", id=first.email_id, label=subject[:60])]
    if first.vessel:
        sources.append(SourceRef(kind="vessel", id=first.vessel, label=first.vessel))
    return ChatAnswer(text=text, sources=sources, review_card=first.proposal_id,
                      review_email_id=first.email_id, llm_status="skipped")  # fmt: skip


def e16_answer_chat(
    request: ChatRequest, context: ChatContext, llm: LlmClient, now: datetime,
    run_tool: Callable[[str, dict], ChatEmail | list[ChatEmail] | None] | None = None,
) -> ChatAnswer:
    """E16 Generate (design_backend.md E16 row, prompts.md 6b). The model only words the answer;
    sources outside the context or a tool result are dropped (S02); the question is scanned
    with the E4 patterns first (S03); a review question gets its card by rule, without the
    model (S04, S05). [AMENDMENT 2026-09-28, read-only tools] With `run_tool` given, the model
    may also call E17/E18 (get_email, search_emails) up to MAX_TOOL_CALLS times, a cap enforced
    here in code, not by the prompt; without it (the default), behaviour is unchanged from
    before tools existed."""
    failed = ChatAnswer(text=CHAT_FAILED, llm_status="failed")
    try:
        if _count_findings(_scan_text(request.question)):
            return failed
    except Exception:  # noqa: BLE001 - a broken scan fails closed
        return failed
    if _CHAT_REVIEW.search(request.question):
        return _review_answer(context)
    user = prompts.e16_user(
        request.question,
        [t.model_dump() for t in request.history],
        _chat_context_json(context),
        now.date().isoformat(),
    )
    allowed = _chat_ids(context)
    try:
        if run_tool is None:
            raw = llm.complete_json("E16", chat_key(request.question), prompts.E16_SYSTEM, user)
            tool_logs: list[ToolCallLog] = []
            cap_reached = False
        else:
            raw, tool_logs, seen, cap_reached = _run_tool_loop(
                llm, chat_key(request.question), prompts.E16_SYSTEM, user, run_tool
            )
            for email in seen:
                allowed["email"].setdefault(email.email_id, email.subject)
        text = str(raw.get("text") or "").strip()
        draft = raw.get("draft")
        draft = str(draft).strip() if draft else None
        if not text and not draft:
            return failed
        sources: list[SourceRef] = []
        for s in raw.get("sources") or []:
            if not isinstance(s, dict):
                continue
            kind, sid = s.get("kind"), str(s.get("id") or "")
            if kind in allowed and sid in allowed[kind] and all(x.id != sid for x in sources):
                label = str(s.get("label") or allowed[kind][sid])[:80]
                sources.append(SourceRef(kind=kind, id=sid, label=label))
        # [AMENDMENT 2026-09-29, protocol/chordx_agent.md 8] "outcome" is a controlled enum, not
        # free prose; the model may self-report one, but RETRIEVAL_LIMIT_REACHED is overridden
        # here whenever it is code-knowable (the loop ran out of tool calls before this answer),
        # so a model that mislabels a budget cutoff as NO_DATA does not get the last word on it.
        outcome = raw.get("outcome")
        outcome = (
            outcome
            if outcome in ("out_of_scope", "no_data", "access_denied", "retrieval_limit_reached", "decision_not_authorized")
            else None
        )  # fmt: skip
        if cap_reached and outcome is not None:
            outcome = "retrieval_limit_reached"
        return ChatAnswer(text=text or "Here is a draft reply.", sources=sources, draft=draft,
                          llm_status="ok", tool_calls=tool_logs, retrieval_outcome=outcome)  # fmt: skip
    except (LlmError, ValidationError, AttributeError, TypeError):
        return failed
