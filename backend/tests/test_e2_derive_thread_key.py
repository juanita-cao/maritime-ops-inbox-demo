"""T2.2 E2 e2_derive_thread_key: scenarios E2-S01 to S07 (design_backend.md sections 10, 10.3,
10.4 and 10.7). Synthetic data with coded names only."""

from datetime import datetime, timedelta, timezone

from src import e_nodes as e
from src.schemas import ParsedEmail, ThreadIndex, ThreadIndexEntry

T0 = datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc)


def email(email_id="E010", subject="RE: VSL-12 V202 redelivery", quoted=()) -> ParsedEmail:
    return ParsedEmail(
        email_id=email_id,
        subject=subject,
        subject_norm=e.normalise_subject(subject),
        sent_time=T0 + timedelta(days=5),
        direction="Inbound",
        sender="mail08@CPY-06.example",
        new_text="Please confirm.",
        quoted_subjects=list(quoted),
    )


def entry(email_id, thread_id, subject, hours=0, quoted=(), vessel=None, voyage=None):
    return ThreadIndexEntry(
        email_id=email_id,
        thread_id=thread_id,
        sent_time=T0 + timedelta(hours=hours),
        subject_norm=e.normalise_subject(subject),
        quoted_subjects_norm=[e.normalise_subject(q) for q in quoted],
        vessel_code=vessel,
        voyage_no=voyage,
    )


def index(*entries) -> ThreadIndex:
    return ThreadIndex(entries=list(entries))


def test_e2_s01_reply_joins_the_thread_of_the_same_subject():
    ref = e.e2_derive_thread_key(
        email(), index(entry("E001", "T-E001", "VSL-12 V202 redelivery", vessel="VSL-12"))
    )
    assert ref.thread_id == "T-E001"
    assert ref.is_new_thread is False
    assert ref.member_email_ids == ["E001", "E010"]
    assert ref.merged_thread_ids == []


def test_e2_s02_new_subject_starts_a_new_thread():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-11 bunker survey"),
        index(entry("E001", "T-E001", "VSL-12 V202 redelivery")),
    )
    assert ref.thread_id == "T-E010"
    assert ref.is_new_thread is True
    assert ref.member_email_ids == ["E010"]
    assert ref.thread_vessel is None and ref.thread_voyage is None


def test_e2_s02_empty_index_starts_a_new_thread():
    ref = e.e2_derive_thread_key(email(), index())
    assert ref.thread_id == "T-E010" and ref.is_new_thread is True


def test_e2_s03_quoted_subject_joins_a_thread_with_another_subject():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-12 hire statement", quoted=["RE: VSL-12 V202 redelivery"]),
        index(entry("E001", "T-E001", "VSL-12 V202 redelivery")),
    )
    assert ref.thread_id == "T-E001" and ref.is_new_thread is False


def test_e2_s03_earlier_email_that_quoted_this_subject_is_linked():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-12 hire statement"),
        index(entry("E001", "T-E001", "VSL-12 V202 redelivery", quoted=["VSL-12 hire statement"])),
    )
    assert ref.thread_id == "T-E001"


def test_e2_s04_email_joining_two_threads_keeps_the_earliest_and_lists_the_other():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-12 hire statement", quoted=["VSL-12 V202 redelivery"]),
        index(
            entry("E001", "T-E001", "VSL-12 V202 redelivery", hours=0),
            entry("E003", "T-E001", "RE: VSL-12 V202 redelivery", hours=2),
            entry("E002", "T-E002", "VSL-12 hire statement", hours=1),
            entry("E009", "T-E009", "VSL-11 noon report", hours=3),
        ),
    )
    assert ref.thread_id == "T-E001"
    assert ref.merged_thread_ids == ["T-E002"]
    assert ref.member_email_ids == ["E001", "E002", "E003", "E010"]  # whole threads, by time


def test_e2_s04_same_first_time_is_broken_by_the_smaller_thread_id():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-12 hire statement", quoted=["VSL-12 V202 redelivery"]),
        index(
            entry("E005", "T-E005", "VSL-12 hire statement", hours=0),
            entry("E004", "T-E004", "VSL-12 V202 redelivery", hours=0),
        ),
    )
    assert ref.thread_id == "T-E004" and ref.merged_thread_ids == ["T-E005"]


def test_e2_s05_hint_comes_from_the_latest_member_with_a_confirmed_vessel():
    ref = e.e2_derive_thread_key(
        email(),
        index(
            entry("E001", "T-E001", "VSL-12 V202 redelivery", 0, vessel="VSL-11", voyage="V77"),
            # the officer corrected E002 to VSL-12; the index holds the final value
            entry("E002", "T-E001", "RE: VSL-12 V202 redelivery", 1, vessel="VSL-12"),
            entry("E003", "T-E001", "RE: VSL-12 V202 redelivery", 2),
        ),
    )
    assert ref.thread_vessel == "VSL-12"
    assert ref.thread_voyage is None  # V77 belongs to another vessel, not mixed in


def test_e2_s05_voyage_hint_is_taken_from_a_member_with_the_same_vessel():
    ref = e.e2_derive_thread_key(
        email(),
        index(
            entry("E001", "T-E001", "VSL-12 V202 redelivery", 0, vessel="VSL-12", voyage="V202"),
            entry("E002", "T-E001", "RE: VSL-12 V202 redelivery", 1, vessel="VSL-12"),
        ),
    )
    assert (ref.thread_vessel, ref.thread_voyage) == ("VSL-12", "V202")


def test_e2_s06_chinese_reply_prefix_joins_the_plain_subject():
    ref = e.e2_derive_thread_key(
        email(subject="回复：转发: VSL-12 V202 Redelivery"),
        index(entry("E001", "T-E001", "VSL-12 V202 redelivery")),
    )
    assert ref.thread_id == "T-E001"


def test_e2_s07_empty_subject_without_quote_is_a_new_thread():
    ref = e.e2_derive_thread_key(
        email(subject=""),
        index(entry("E001", "T-E001", ""), entry("E002", "T-E002", "RE: ")),
    )
    assert ref.thread_id == "T-E010" and ref.is_new_thread is True


def test_e2_s07_empty_quoted_subject_is_not_a_key():
    ref = e.e2_derive_thread_key(
        email(subject="VSL-11 bunker survey", quoted=["", "Fw:"]),
        index(entry("E001", "T-E001", "", quoted=[""])),
    )
    assert ref.is_new_thread is True


def test_e2_s01_spaces_around_punctuation_do_not_split_a_thread():
    assert e.normalise_subject("M/V VSL-12// NOON REPORT 20260723") == e.normalise_subject(
        "M/V VSL-12//noon report 20260723"
    )
    ref = e.e2_derive_thread_key(
        email(subject="M/V VSL-12// NOON REPORT 20260723"),
        index(entry("E001", "T-E001", "M/V VSL-12//noon report 20260723")),
    )
    assert ref.thread_id == "T-E001"


def test_e2_s02_different_words_are_still_different_subjects():
    assert e.normalise_subject("VSL-12 noon report") != e.normalise_subject("VSL-02noon report")


# --- review 2026-09-26: chronology with the current email, undated entries -------------

SUBJ = "VSL-12 V202 redelivery"


def undated(email_id, thread_id, vessel=None, voyage=None):
    return entry(email_id, thread_id, SUBJ).model_copy(
        update={"sent_time": None, "vessel_code": vessel, "voyage_no": voyage}
    )


def at(email_id, hours):
    return email(email_id).model_copy(update={"sent_time": T0 + timedelta(hours=hours)})


def test_e2_s01_current_email_earlier_than_existing_members_comes_first():
    ref = e.e2_derive_thread_key(at("E001", 0), index(entry("E002", "T-E002", SUBJ, hours=2)))
    assert ref.member_email_ids == ["E001", "E002"]


def test_e2_s01_current_email_between_two_members_is_placed_by_time():
    ref = e.e2_derive_thread_key(
        at("E005", 3),
        index(entry("E002", "T-E002", SUBJ, hours=2), entry("E009", "T-E002", SUBJ, hours=4)),
    )
    assert ref.member_email_ids == ["E002", "E005", "E009"]


def test_e2_s01_current_email_without_time_goes_last():
    ref = e.e2_derive_thread_key(
        email("E001").model_copy(update={"sent_time": None}),
        index(entry("E002", "T-E002", SUBJ, hours=2)),
    )
    assert ref.member_email_ids == ["E002", "E001"]


def test_e2_s01_several_undated_members_are_ordered_by_id():
    ref = e.e2_derive_thread_key(
        email("E004").model_copy(update={"sent_time": None}),
        index(undated("E007", "T-E001"), entry("E001", "T-E001", SUBJ), undated("E003", "T-E001")),
    )
    assert ref.member_email_ids == ["E001", "E003", "E004", "E007"]


def test_e2_s05_undated_conflicting_vessel_does_not_outrank_a_dated_one():
    ref = e.e2_derive_thread_key(
        email(),
        index(
            entry("E001", "T-E001", SUBJ, 0, vessel="VSL-12"),
            undated("E002", "T-E001", vessel="VSL-11"),
        ),
    )
    assert ref.thread_vessel == "VSL-12"


def test_e2_s05_voyage_comes_from_an_older_dated_member_of_the_same_vessel():
    ref = e.e2_derive_thread_key(
        email(),
        index(
            entry("E001", "T-E001", SUBJ, 0, vessel="VSL-12", voyage="V202"),
            entry("E002", "T-E001", SUBJ, 5, vessel="VSL-12"),
            undated("E003", "T-E001", vessel="VSL-11", voyage="V301"),
        ),
    )
    assert (ref.thread_vessel, ref.thread_voyage) == ("VSL-12", "V202")


def test_e2_s05_only_undated_members_give_the_hint_as_a_fallback():
    ref = e.e2_derive_thread_key(
        email(), index(undated("E002", "T-E001", vessel="VSL-11", voyage="V301"))
    )
    assert (ref.thread_vessel, ref.thread_voyage) == ("VSL-11", "V301")


def test_e2_s04_characterization_same_generic_subject_joins_unrelated_threads():
    """Current contract (T2.2): one shared normalised subject is enough to link. Generic subjects
    such as "Noon Report" therefore join unrelated threads; changing this needs an amendment."""
    ref = e.e2_derive_thread_key(
        email("E010", subject="Noon Report"),
        index(
            entry("E001", "T-E001", "Noon Report", 0, vessel="VSL-11"),
            entry("E002", "T-E002", "RE: noon report", 1, vessel="VSL-12"),
        ),  # fmt: skip
    )
    assert ref.thread_id == "T-E001" and ref.merged_thread_ids == ["T-E002"]
    assert ref.thread_vessel == "VSL-12"  # the hint then crosses the merged threads


def test_e2_email_already_in_the_index_is_listed_once():
    ref = e.e2_derive_thread_key(
        at("E002", 2), index(entry("E001", "T-E001", SUBJ, 0), entry("E002", "T-E001", SUBJ, 2))
    )
    assert ref.member_email_ids == ["E001", "E002"]
