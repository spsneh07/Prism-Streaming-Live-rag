import time

from app.sessions.store import Session, SessionStore


def test_session_lifecycle_and_expiry():
    st = SessionStore(ttl_s=0.05)
    s = st.create()
    assert st.get(s.session_id) is s
    time.sleep(0.08)
    assert st.get(s.session_id) is None          # expired: memory is ephemeral


def test_sessions_are_isolated_and_anonymous():
    st = SessionStore()
    a, b = st.create(), st.create()
    a.start_topic("travel")
    assert b.topic_utterance is None and a.session_id != b.session_id
    assert not {"user", "user_id", "profile", "email"} & set(Session.__dataclass_fields__)
    assert st.end(a.session_id) and st.get(a.session_id) is None
