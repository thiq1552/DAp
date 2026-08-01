from datetime import datetime, timedelta, timezone

import pytest

from ccbus.store import Store, StoreError


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "bus.db", max_body_bytes=1000)
    yield s
    s.close()


def post(store, key, body="x", agent="ubuntu-16g", kind="output", tags=None, project="p"):
    return store.put_entry(
        project=project, key=key, summary=f"tóm tắt {key}", body=body,
        kind=kind, tags=tags or [], agent=agent,
    )


def test_reposting_a_key_versions_instead_of_overwriting(store):
    assert post(store, "api/schema", "v1")["version"] == 1
    assert post(store, "api/schema", "v2")["version"] == 2
    assert store.get_entry(project="p", key="api/schema")["body"] == "v2"
    assert store.get_entry(project="p", key="api/schema", version=1)["body"] == "v1"


def test_body_over_limit_is_rejected_with_actionable_message(store):
    with pytest.raises(StoreError, match="vượt giới hạn"):
        post(store, "big", "x" * 1001)


def test_projects_are_isolated(store):
    post(store, "shared/key", project="alpha")
    assert store.get_entry(project="beta", key="shared/key") is None
    assert store.list_entries(project="alpha", limit=10)[0]["key"] == "shared/key"


def test_list_returns_only_latest_version_per_key(store):
    post(store, "a", "1")
    post(store, "a", "2")
    post(store, "b", "1")
    listed = store.list_entries(project="p", limit=10)
    assert sorted((e["key"], e["version"]) for e in listed) == [("a", 2), ("b", 1)]


def test_list_filters_by_kind_tag_and_agent(store):
    post(store, "a", kind="decision", tags=["api"], agent="mac")
    post(store, "b", kind="output", tags=["db"], agent="ubuntu-8g-a")
    assert [e["key"] for e in store.list_entries(project="p", kind="decision")] == ["a"]
    assert [e["key"] for e in store.list_entries(project="p", tag="db")] == ["b"]
    assert [e["key"] for e in store.list_entries(project="p", agent="mac")] == ["a"]


def test_tag_filter_does_not_match_a_substring_of_another_tag(store):
    post(store, "a", tags=["api-v2"])
    assert store.list_entries(project="p", tag="api") == []


def test_search_matches_body_and_returns_a_snippet(store):
    post(store, "perf/bench", body="warmup done. throughput 120 rps steady. teardown ok")
    hit = store.search_entries(project="p", query="120 rps")[0]
    assert hit["key"] == "perf/bench"
    assert "120 rps" in hit["snippet"]


def test_search_treats_wildcards_as_literal_text(store):
    post(store, "a", body="plain text")
    assert store.search_entries(project="p", query="%") == []


def test_claim_hands_each_task_to_exactly_one_machine(store):
    store.add_task(project="p", title="t1")
    store.add_task(project="p", title="t2")
    first = store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3)
    second = store.claim_task(project="p", agent="ubuntu-8g-a", claim_ttl_s=60, max_attempts=3)
    third = store.claim_task(project="p", agent="ubuntu-8g-b", claim_ttl_s=60, max_attempts=3)
    assert {first["id"], second["id"]} == {t["id"] for t in store.list_tasks(project="p")}
    assert first["id"] != second["id"]
    assert third is None


def test_task_is_not_claimable_until_its_dependency_is_published(store):
    store.add_task(project="p", title="dùng schema", depends_on=["api/schema"])
    assert store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3) is None

    post(store, "api/schema", "nội dung schema")
    claimed = store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3)
    assert claimed["title"] == "dùng schema"
    assert claimed["dependencies"][0] == {
        "key": "api/schema", "version": 1, "summary": "tóm tắt api/schema",
        "agent": "ubuntu-16g", "available": True,
    }


def test_priority_wins_over_insertion_order(store):
    store.add_task(project="p", title="thường")
    store.add_task(project="p", title="gấp", priority=5)
    assert store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3)["title"] == "gấp"


def test_task_from_a_dead_machine_is_requeued(store):
    store.add_task(project="p", title="t1")
    store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3)
    assert store.claim_task(project="p", agent="ubuntu-8g-a", claim_ttl_s=60, max_attempts=3) is None

    # ttl=0 nghĩa là lần nhận trước đã quá hạn
    retaken = store.claim_task(project="p", agent="ubuntu-8g-a", claim_ttl_s=0, max_attempts=3)
    assert retaken["owner"] == "ubuntu-8g-a"
    assert retaken["attempts"] == 2


def test_task_that_keeps_expiring_eventually_goes_dead(store):
    store.add_task(project="p", title="hỏng")
    for _ in range(2):
        store.claim_task(project="p", agent="mac", claim_ttl_s=0, max_attempts=2)
    assert store.claim_task(project="p", agent="mac", claim_ttl_s=0, max_attempts=2) is None
    assert store.list_tasks(project="p")[0]["status"] == "dead"


def test_failed_task_returns_to_the_queue_until_attempts_run_out(store):
    task = store.add_task(project="p", title="t1")
    store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=2)
    assert store.finish_task(task_id=task["id"], agent="mac", status="failed", max_attempts=2)["status"] == "open"

    store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=2)
    assert store.finish_task(task_id=task["id"], agent="mac", status="failed", max_attempts=2)["status"] == "dead"


def test_finishing_a_task_twice_is_rejected(store):
    task = store.add_task(project="p", title="t1")
    store.claim_task(project="p", agent="mac", claim_ttl_s=60, max_attempts=3)
    store.finish_task(task_id=task["id"], agent="mac", status="done")
    with pytest.raises(StoreError, match="trạng thái cuối"):
        store.finish_task(task_id=task["id"], agent="mac", status="done")


def test_lock_blocks_a_second_machine_but_is_reentrant_for_the_holder(store):
    assert store.acquire_lock(project="p", resource="src/auth/", owner="mac", ttl_s=60)["acquired"]
    blocked = store.acquire_lock(project="p", resource="src/auth/", owner="ubuntu-8g-a", ttl_s=60)
    assert blocked == {
        "acquired": False, "resource": "src/auth/", "held_by": "mac",
        "expires_in_s": blocked["expires_in_s"], "note": "",
    }
    assert store.acquire_lock(project="p", resource="src/auth/", owner="mac", ttl_s=60)["acquired"]


def test_expired_lock_is_free_for_anyone(store):
    store.acquire_lock(project="p", resource="r", owner="mac", ttl_s=0)
    assert store.acquire_lock(project="p", resource="r", owner="ubuntu-8g-a", ttl_s=60)["acquired"]
    assert [lock["held_by"] for lock in store.list_locks(project="p")] == ["ubuntu-8g-a"]


def test_only_the_holder_can_release_a_lock(store):
    store.acquire_lock(project="p", resource="r", owner="mac", ttl_s=60)
    assert store.release_lock(project="p", resource="r", owner="ubuntu-8g-a")["released"] is False
    assert store.release_lock(project="p", resource="r", owner="mac")["released"] is True
    assert store.list_locks(project="p") == []


def test_agent_presence_tracks_last_seen_and_online_window(store):
    store.touch_agent(name="mac", project="p")
    store.touch_agent(name="mac", project="p")
    agent = store.list_agents(within_s=600)[0]
    assert (agent["name"], agent["calls"], agent["online"]) == ("mac", 2, True)


def test_agent_last_seen_long_ago_is_reported_offline(store):
    store.touch_agent(name="mac", project="p")
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    store._conn.execute("UPDATE agents SET last_seen = ? WHERE name = 'mac'", (long_ago,))
    assert store.list_agents(within_s=900)[0]["online"] is False


def test_stats_and_projects_summarise_the_board(store):
    post(store, "a", project="alpha")
    store.add_task(project="alpha", title="t1")
    stats = store.stats(project="alpha")
    assert (stats["entry_keys"], stats["tasks"]) == (1, {"open": 1})
    assert store.projects() == ["alpha"]
