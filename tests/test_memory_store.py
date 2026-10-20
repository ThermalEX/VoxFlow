import pytest

from voxflow.memory_store import FOREVER, KEEP_SECONDS, WEEK, MemoryStore, day_of


class Clock:
    def __init__(self, now=1_760_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    memory = MemoryStore(tmp_path / "memory" / "memory.db", clock=clock)
    yield memory
    memory.close()


def test_entries_from_the_user_are_kept_forever_and_extracted_ones_for_a_week(store):
    explicit = store.add_entry("周三下午三点开评审会", source="explicit")
    extracted = store.add_entry("王书涵", kind="person", source="auto")
    assert (explicit.keep, extracted.keep) == (FOREVER, WEEK)
    assert extracted.kind == "person"
    assert [entry.content for entry in store.entries()] == ["王书涵", "周三下午三点开评审会"]


def test_a_repeated_mention_refreshes_the_entry_and_never_shortens_it(store, clock):
    first = store.add_entry("王书涵", kind="person", source="auto")
    clock.now += 60
    again = store.add_entry(" 王书涵。", source="explicit", detail={"note": "me"})
    assert again.id == first.id
    assert (again.keep, again.source, again.detail) == (FOREVER, "explicit", {"note": "me"})
    assert again.updated_at == clock.now
    assert len(store.entries()) == 1
    store.add_entry("王书涵", source="auto")
    assert store.entry(first.id).keep == FOREVER


def test_blank_entries_and_records_are_ignored(store):
    assert store.add_entry("  ，。 ") is None
    assert store.add_record("   ") is None
    assert store.entries() == [] and store.records() == []


def test_entries_can_be_edited_searched_and_listed_as_names(store):
    entry = store.add_entry("王淑涵", kind="person")
    store.add_entry("VoxFlow", kind="term")
    store.add_entry("周五交周报")
    store.update_entry(entry.id, content="王书涵")
    store.update_entry(entry.id, content="  ")  # a blank edit keeps the old text
    assert store.entry(entry.id).content == "王书涵"
    assert [item.content for item in store.entries(search="周报")] == ["周五交周报"]
    assert sorted(store.names()) == ["VoxFlow", "王书涵"]


def test_records_are_grouped_by_day_and_track_extraction(store, clock):
    first = store.add_record("明天上午十点开会。")
    clock.now += 24 * 3600
    second = store.add_record("记得带电脑。")
    assert [day for day in store.days()] == [day_of(clock.now), day_of(clock.now - 24 * 3600)]
    assert [record.text for record in store.records(day_of(clock.now))] == ["记得带电脑。"]
    store.mark_extracted(first.id)
    assert [record.id for record in store.pending_records()] == [second.id]


def test_a_new_summary_replaces_the_old_one_but_keeps_its_keep(store):
    store.save_summary("2026-10-19", "第一版")
    store.set_keep("summaries", store.summary("2026-10-19").id, FOREVER)
    saved = store.save_summary("2026-10-19", "第二版")
    assert (saved.text, saved.keep) == ("第二版", FOREVER)
    assert store.days() == ["2026-10-19"]


def test_week_rows_are_forgotten_after_seven_days_and_forever_rows_stay(store, clock):
    week_entry = store.add_entry("临时会议室 B2", source="auto")
    forever_entry = store.add_entry("王书涵", kind="person", source="explicit")
    record = store.add_record("今天下午去取快递。")
    kept_record = store.add_record("项目代号是北极星。")
    store.set_keep("records", kept_record.id, FOREVER)
    clock.now += KEEP_SECONDS - 1
    assert store.purge() == 0
    clock.now += 2
    assert store.purge() == 2
    assert store.entry(week_entry.id) is None and store.record(record.id) is None
    assert store.entry(forever_entry.id) is not None and store.record(kept_record.id) is not None


def test_moving_a_row_back_to_a_week_starts_its_week_now(store, clock):
    record = store.add_record("项目代号是北极星。")
    store.set_keep("records", record.id, FOREVER)
    clock.now += 30 * 24 * 3600
    store.set_keep("records", record.id, WEEK)
    assert store.purge() == 0
    clock.now += KEEP_SECONDS + 1
    assert store.purge() == 1


def test_delete_day_clear_and_bad_arguments(store):
    store.add_record("今天的第一句。")
    day = store.days()[0]
    store.save_summary(day, "总结")
    store.add_entry("王书涵")
    store.delete_day(day)
    assert store.days() == [] and len(store.entries()) == 1
    store.clear()
    assert store.entries() == []
    with pytest.raises(ValueError):
        store.set_keep("records", 1, "month")
    with pytest.raises(ValueError):
        store.delete("users", 1)


def test_the_database_survives_reopening(tmp_path, clock):
    path = tmp_path / "memory.db"
    first = MemoryStore(path, clock=clock)
    first.add_entry("王书涵", kind="person")
    first.close()
    second = MemoryStore(path, clock=clock)
    assert [entry.content for entry in second.entries()] == ["王书涵"]
    second.close()
