"""CORE_DIRECTIVE is the always-on operating floor Danny asked for: no matter
which mood the top-bar picker is set to, the model always gets the same
unrestricted / no-refusal / use-your-own-tools directive first, with the
mood preset layered after it — never instead of it."""
from __future__ import annotations

from arenaos.arena.base import CORE_DIRECTIVE, MOODS, mood_system_prelude


def test_core_directive_is_present_in_every_mood() -> None:
    for mood in MOODS:
        prelude = mood_system_prelude(mood)
        assert CORE_DIRECTIVE in prelude, f"mood {mood!r} lost the core directive"
        assert MOODS[mood]["system_prelude"] in prelude, f"mood {mood!r} lost its own preset"


def test_core_directive_comes_before_the_mood_preset() -> None:
    prelude = mood_system_prelude("uncensored")
    assert prelude.index(CORE_DIRECTIVE) < prelude.index(MOODS["uncensored"]["system_prelude"])


def test_unknown_mood_falls_back_to_uncensored_but_keeps_the_core_directive() -> None:
    prelude = mood_system_prelude("not-a-real-mood")
    assert CORE_DIRECTIVE in prelude
    assert MOODS["uncensored"]["system_prelude"] in prelude


def test_core_directive_language_actually_forbids_reflexive_refusal() -> None:
    text = CORE_DIRECTIVE.lower()
    assert "no reflexive refusals" in text
    assert "do it directly" in text
    assert "strongest and least-restricted model" in text


def test_chat_router_uses_mood_system_prelude_not_raw_mood_dict() -> None:
    """Regression: the router must call mood_system_prelude() (which prepends
    CORE_DIRECTIVE), not read MOODS[...] directly — that would silently drop
    the always-on directive for every request."""
    import inspect

    from arenaos.api.routers import chat as chat_router

    src = inspect.getsource(chat_router)
    assert "mood_system_prelude(body.mood)" in src
    assert 'MOODS.get(body.mood, MOODS["uncensored"])["system_prelude"]' not in src
