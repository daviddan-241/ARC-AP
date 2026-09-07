"""Auto-learn: heuristic fact extraction + dedupe persistence."""
from arenaos.memory.autolearn import AutoLearner, extract_facts
from arenaos.memory.store import MemoryStore


def test_extract_name_and_preference():
    facts = extract_facts("Hey, my name is Daniel and I like dark minimal UIs by the way")
    keys = {k for k, _ in facts}
    values = " ".join(v for _, v in facts)
    assert "profile.name" in keys
    assert "Daniel" in values
    assert "preference" in keys
    assert "dark minimal UIs" in values


def test_extract_remember_and_never():
    facts = extract_facts("Remember that my deploy target is Render. Also never push on Fridays.")
    kinds = [k for k, _ in facts]
    contents = " ".join(v for _, v in facts).lower()
    assert "instruction" in kinds or "instruction.never" in kinds
    assert "deploy target is render" in contents
    assert "push on fridays" in contents


def test_extract_ignores_nonfacts():
    facts = extract_facts("What is the capital of France? Also it rains a lot in this code")
    assert facts == []


def test_learner_persists_and_dedupes():
    store = MemoryStore()
    learner = AutoLearner(store)
    first = learner.learn_from_message("My name is Daniel")
    assert len(first) == 1
    assert first[0]["key"] == "profile.name"
    second = learner.learn_from_message("my name is Daniel")  # dup — no re-store
    assert second == []
    hits = store.search("daniel", layer="long")
    assert len(hits) == 1
    assert hits[0]["source"] == "autolearn"


def test_learner_disabled():
    store = MemoryStore()
    learner = AutoLearner(store, enabled=False)
    assert learner.learn_from_message("my name is Daniel") == []
