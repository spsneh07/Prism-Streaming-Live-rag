import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def rt():
    """One shared runtime (models load once per test session)."""
    from app.runtime import Runtime
    return Runtime.load()


@pytest.fixture
def run(rt):
    """Run turns through an engine at 20x pacing; returns (session, [TurnResult])."""
    import asyncio

    def _run(turns, engine=None, session=None):
        eng = engine or rt.engine()
        s = session or rt.sessions.create()
        out = []
        for chunks, end_t in turns:
            chunks = [{"t": t, "text": x} for t, x in chunks]
            out.append(asyncio.run(eng.run_turn(s, chunks, end_t, speed=20.0)))
        return s, out
    return _run


def types(result):
    return [e["type"] for e in result.log.events]
