"""Tests for Honcho session context peer resolution."""

from types import SimpleNamespace

from plugins.memory.honcho.session import (
    HonchoAuthError,
    HonchoSession,
    HonchoSessionManager,
)


class _FakeSummary:
    content = "summary"


class _FakeContext:
    summary = _FakeSummary()
    peer_representation = "representation"
    peer_card = ["fact"]
    messages = []


class _RecordingHonchoSession:
    def __init__(self):
        self.calls = []

    def context(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeContext()


def _manager_with_cached_session(*, ai_observe_others=True):
    cfg = SimpleNamespace(
        write_frequency="turn",
        dialectic_reasoning_level="low",
        dialectic_dynamic=True,
        dialectic_max_chars=600,
        observation_mode="directional",
        user_observe_me=True,
        user_observe_others=True,
        ai_observe_me=True,
        ai_observe_others=ai_observe_others,
        message_max_chars=25000,
        dialectic_max_input_chars=10000,
    )
    mgr = HonchoSessionManager(honcho=SimpleNamespace(), config=cfg)
    session = HonchoSession(
        key="test-session",
        user_peer_id="chris",
        assistant_peer_id="hermes",
        honcho_session_id="test-session",
    )
    fake_honcho_session = _RecordingHonchoSession()
    mgr._cache[session.key] = session
    mgr._sessions_cache[session.honcho_session_id] = fake_honcho_session
    return mgr, fake_honcho_session


def test_session_context_user_alias_uses_assistant_observer_when_ai_can_observe_others():
    mgr, fake = _manager_with_cached_session(ai_observe_others=True)

    result = mgr.get_session_context("test-session", peer="user")

    assert result["summary"] == "summary"
    assert fake.calls == [
        {
            "summary": True,
            "tokens": None,
            "peer_target": "chris",
            "peer_perspective": "hermes",
        }
    ]


def test_session_context_explicit_user_peer_matches_user_alias():
    mgr, fake = _manager_with_cached_session(ai_observe_others=True)

    mgr.get_session_context("test-session", peer="chris")

    assert fake.calls == [
        {
            "summary": True,
            "tokens": None,
            "peer_target": "chris",
            "peer_perspective": "hermes",
        }
    ]


def test_session_context_user_alias_uses_user_self_observer_when_ai_cannot_observe_others():
    mgr, fake = _manager_with_cached_session(ai_observe_others=False)

    mgr.get_session_context("test-session", peer="user")

    assert fake.calls == [
        {
            "summary": True,
            "tokens": None,
            "peer_target": "chris",
            "peer_perspective": "chris",
        }
    ]


class _UnexpectedPeerCreation(BaseException):
    """Raised by the fake SDK if search calls Honcho.peer()."""


class _SearchHoncho:
    def __init__(self, primary_messages):
        self.primary_messages = primary_messages
        self.search_calls = []

    def search(self, query, filters, limit):
        self.search_calls.append((query, filters, limit))
        if isinstance(self.primary_messages, Exception):
            raise self.primary_messages
        return self.primary_messages

    def peer(self, peer_id):
        raise _UnexpectedPeerCreation(
            f"honcho_search fallback must not create peer {peer_id!r}"
        )


def _search_manager(monkeypatch, primary_messages, fallback_messages):
    """Build a search manager whose fallback can never call Honcho.peer()."""
    mgr, _ = _manager_with_cached_session()
    fake_honcho = _SearchHoncho(primary_messages)
    constructed_peers = []

    class _ReadOnlyPeer:
        def __init__(self, peer_id, honcho):
            assert peer_id == "chris"
            assert honcho is fake_honcho
            constructed_peers.append(peer_id)

        def search(self, query, limit):
            assert (query, limit) == ("older fact", 5)
            return fallback_messages

    monkeypatch.setattr(
        "plugins.memory.honcho.session.get_honcho_client",
        lambda config: fake_honcho,
    )
    monkeypatch.setattr("honcho.peer.Peer", _ReadOnlyPeer)
    monkeypatch.setattr(mgr, "_authed_call", lambda op_name, operation: operation())
    return mgr, fake_honcho, constructed_peers


def test_search_context_keeps_primary_hit_and_skips_fallback(monkeypatch):
    message = SimpleNamespace(
        content="Chris said this in this session.", peer_id="chris", session_id="session"
    )
    mgr, fake_honcho, constructed_peers = _search_manager(monkeypatch, [message], [])

    result = mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")

    assert "Chris said this in this session." in result
    assert fake_honcho.search_calls == [("older fact", {"peer_perspective": "chris"}, 5)]
    assert constructed_peers == []


def test_search_context_falls_back_when_perspective_search_is_empty(monkeypatch):
    """An empty perspective result must not hide peer-authored history."""
    message = SimpleNamespace(
        content="Chris said this in an older session.",
        peer_id="chris",
        session_id="older-session",
    )
    mgr, fake_honcho, constructed_peers = _search_manager(monkeypatch, [], [message])

    result = mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")

    assert "Chris said this in an older session." in result
    assert fake_honcho.search_calls == [("older fact", {"peer_perspective": "chris"}, 5)]
    assert constructed_peers == ["chris"]


def test_search_context_falls_back_when_perspective_search_raises(monkeypatch):
    message = SimpleNamespace(
        content="Chris said this in an older session.",
        peer_id="chris",
        session_id="older-session",
    )
    mgr, fake_honcho, constructed_peers = _search_manager(
        monkeypatch, RuntimeError("unsupported filter"), [message]
    )

    result = mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")

    assert "Chris said this in an older session." in result
    assert fake_honcho.search_calls == [("older fact", {"peer_perspective": "chris"}, 5)]
    assert constructed_peers == ["chris"]


def test_search_context_returns_empty_when_primary_and_fallback_miss(monkeypatch):
    mgr, fake_honcho, constructed_peers = _search_manager(monkeypatch, [], [])

    result = mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")

    assert result == ""
    assert fake_honcho.search_calls == [("older fact", {"peer_perspective": "chris"}, 5)]
    assert constructed_peers == ["chris"]


def test_search_context_propagates_primary_auth_failure_without_fallback(monkeypatch):
    mgr, _fake_honcho, constructed_peers = _search_manager(monkeypatch, [], [])

    def _auth_failure(op_name, operation):
        assert op_name == "message search"
        raise HonchoAuthError("primary rejected")

    monkeypatch.setattr(mgr, "_authed_call", _auth_failure)
    try:
        mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")
    except HonchoAuthError as exc:
        assert str(exc) == "primary rejected"
    else:
        raise AssertionError("expected primary authentication failure")
    assert constructed_peers == []


def test_search_context_propagates_fallback_auth_failure_without_peer_creation(monkeypatch):
    mgr, _fake_honcho, constructed_peers = _search_manager(monkeypatch, [], [])
    calls = []

    def _auth_failure(op_name, operation):
        calls.append(op_name)
        if op_name == "peer search":
            raise HonchoAuthError("fallback rejected")
        return operation()

    monkeypatch.setattr(mgr, "_authed_call", _auth_failure)
    try:
        mgr.search_context("test-session", "older fact", max_tokens=400, peer="user")
    except HonchoAuthError as exc:
        assert str(exc) == "fallback rejected"
    else:
        raise AssertionError("expected fallback authentication failure")
    assert calls == ["message search", "peer search"]
    assert constructed_peers == []
