"""Root pytest configuration.

Session-wide setup that has to happen *before* any ``app.*`` module is
imported:

* ``app.api.auth`` imports ``talkingdb.helpers.jwt``, which raises
  ``RuntimeError`` at *import time* if ``JWT_SECRET_KEY`` is not set. Pytest
  imports conftest.py files before it imports test modules, so setting the
  env var here (at module import time, not inside a fixture) guarantees it
  exists before anything under ``tests/`` triggers that import chain.
* A handful of other env-driven module-level constants (``talkingdb``
  spool/client settings) are given deterministic test values for the same
  reason - so behaviour doesn't depend on whatever happens to be in the
  shell environment a given test run.

Everything else (temporary SQLite databases, FastAPI app construction,
etc.) lives in the more specific ``tests/<layer>/conftest.py`` files next to
the tests that need it.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-pytest")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")

# talkingdb.helpers.client reads this at import time; keep tests hermetic
# and independent of any real Content-Elementizer service.
os.environ.setdefault("CLIENT_MODE", "direct")


# --------------------------------------------------------------------------
# Real-SQLite fixtures shared by unit, api, integration, and e2e tests.
#
# ``talkingdb.clients.sqlite`` caches one connection per thread in a module
# level ``threading.local`` and reads its DB path (``GRAPH_DB``) once, from
# an env var, at import time. To get a fresh, isolated database per test we:
#
# 1. Point the module's ``GRAPH_DB`` attribute at a per-test temp file.
# 2. Drop any cached thread-local connection so the next ``sqlite_conn()``
#    call opens a brand new connection against the new path.
#
# This is real SQLite on disk (not an in-memory stub), exercising the
# actual schema-creation and query code in the ``talkingdb`` store modules -
# these fixtures live at the top level so every test layer can use them.
# --------------------------------------------------------------------------


def _drop_cached_connection() -> None:
    import talkingdb.clients.sqlite as sqlite_client

    conn = getattr(sqlite_client._thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        del sqlite_client._thread_local.conn


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """Point talkingdb's sqlite client at an empty, isolated temp DB file.

    Schema is NOT created here - callers use ``initialized_db`` (or call the
    relevant ``*_store.init_db`` themselves) so tests that specifically want
    to exercise ``init_db`` idempotency can do so against a truly blank file.
    """
    import talkingdb.clients.sqlite as sqlite_client

    db_path = tmp_path / "test_graphs.db"
    monkeypatch.setattr(sqlite_client, "GRAPH_DB", str(db_path))
    _drop_cached_connection()
    yield str(db_path)
    _drop_cached_connection()


@pytest.fixture
def initialized_db(sqlite_db):
    """A temp SQLite DB with every importable store's schema created.

    Mirrors app.services.workers.init_database(), minus the project_store /
    file_graph_store / ensure_bucket() calls - those live in modules that
    currently fail to import (see tests/known_issues), so their schemas
    aren't needed by anything under test.
    """
    import talkingdb.clients.sqlite as sqlite_client
    from talkingdb.helpers.job import store as job_store
    from talkingdb.helpers.namespace import store as namespace_store
    from talkingdb.models.auth.api_key import APIKeyModel
    from talkingdb.models.auth.user import UserModel
    from talkingdb.models.graph.graph import GraphModel

    with sqlite_client.sqlite_conn() as conn:
        GraphModel.init_db(conn)
        UserModel.init_db(conn)
        APIKeyModel.init_db(conn)
        job_store.init_db(conn)
        namespace_store.init_db(conn)
        namespace_store.ensure_reserved(conn)
    return sqlite_db


@pytest.fixture
def make_user(initialized_db):
    """Factory: create a user (email, plaintext password) -> UserModel."""

    def _make(email: str = "alice@example.com", password: str = "correct-horse-battery"):
        import talkingdb.clients.sqlite as sqlite_client
        from talkingdb.helpers.auth import hash_password
        from talkingdb.models.auth.user import UserModel

        with sqlite_client.sqlite_conn() as conn:
            return UserModel.create(
                conn=conn, email=email, password_hash=hash_password(password)
            )

    return _make


@pytest.fixture
def make_api_key(initialized_db):
    """Factory: create an API key for an (existing or new) user email."""

    def _make(user_email: str = "alice@example.com"):
        import talkingdb.clients.sqlite as sqlite_client
        from talkingdb.models.auth.api_key import APIKeyModel

        with sqlite_client.sqlite_conn() as conn:
            return APIKeyModel.create(conn=conn, user_email=user_email)

    return _make


# --------------------------------------------------------------------------
# Partial FastAPI app + TestClient, shared by api/ and e2e/ tests.
#
# ``app.main`` cannot currently be imported (see tests/known_issues - it
# transitively pulls in app.api.documents and app.api.projects, both of
# which fail to import at the dependency revisions pinned in
# pyproject.toml). None of the routes under test come from those two
# routers, so instead of skipping API-level testing altogether we assemble
# a FastAPI app from just the routers that *do* import cleanly: everything
# app.main would mount except documents and projects.
#
# This app also skips app.main's lifespan (which calls
# app.services.workers.init_database - also unimportable) and instead
# relies on the initialized_db fixture above to set up the same tables
# directly against a temp SQLite file.
# --------------------------------------------------------------------------


def _build_partial_app():
    from fastapi import FastAPI

    from app.api import auth, index, jobs, namespaces, public, queries, root, tree

    app = FastAPI(title="Module TalkingDB (test app, partial router set)")
    app.include_router(root.router)
    app.include_router(auth.router)
    app.include_router(namespaces.router)
    app.include_router(jobs.router)
    app.include_router(queries.router)
    app.include_router(tree.router)
    app.include_router(index.router)
    app.include_router(public.router)
    return app


@pytest.fixture
def app():
    return _build_partial_app()


@pytest.fixture
def client(app, initialized_db):
    """A TestClient wired to a real, isolated, schema-initialized SQLite DB."""
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(make_user, make_api_key):
    """Bearer-auth headers for a freshly created user + API key."""
    make_user(email="alice@example.com", password="correct-horse-battery")
    api_key_obj = make_api_key(user_email="alice@example.com")
    return {"Authorization": f"Bearer {api_key_obj.api_key}"}


# --------------------------------------------------------------------------
# Fake spaCy backend for app.services.package_text_tokenizer.TextTokenizer.
#
# TextTokenizer lazily calls ``spacy.load("en_core_web_md")`` on first use.
# Downloading/loading the real model is slow, needs network access, and
# would make tokenizer behaviour (and therefore extractor/query-ranking
# behaviour) depend on a large opaque third-party model rather than on our
# code. For unit/API tests we substitute a small, deterministic fake spaCy
# pipeline that implements just the attributes TextTokenizer actually reads
# (``text``, ``lemma_``, ``is_alpha``, ``is_stop``, ``is_space``,
# ``is_punct``) plus a no-op Matcher (compound-phrase matching is not
# exercised by these tests; TextTokenizer degrades gracefully to per-token
# output when the matcher finds nothing, which is exactly what we want to
# test against).
# --------------------------------------------------------------------------

_FAKE_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "of",
    "to", "for", "and", "or", "but", "with", "as", "by", "it", "this",
    "that", "be", "been",
}
_FAKE_PUNCT = set(".,;:!?()[]{}\"'`")


class _FakeToken:
    def __init__(self, text: str):
        self.text = text
        self.is_space = text.isspace()
        self.is_punct = text in _FAKE_PUNCT
        self.is_alpha = text.isalpha()
        self.is_stop = text.lower() in _FAKE_STOPWORDS
        # Cheap deterministic "lemma": lowercase, drop a single trailing 's'
        # off words of >3 chars so e.g. "drugs" -> "drug" without a real
        # morphological analyzer.
        lower = text.lower()
        if self.is_alpha and len(lower) > 3 and lower.endswith("s"):
            lower = lower[:-1]
        self.lemma_ = lower


class _FakeVocab:
    def __init__(self):
        self.strings = {}


class _FakeDoc(list):
    pass


class _FakeNLP:
    def __init__(self):
        self.vocab = _FakeVocab()

    def __call__(self, text: str) -> _FakeDoc:
        import re

        raw_tokens = re.findall(r"\w+(?:\.\w+)*|[^\w\s]", text, flags=re.UNICODE)
        return _FakeDoc(_FakeToken(t) for t in raw_tokens)


class _FakeMatcher:
    """No-op stand-in for spacy.matcher.Matcher: never matches a compound."""

    def __init__(self, vocab, *args, **kwargs):
        self._vocab = vocab

    def add(self, name, patterns):
        pass

    def __call__(self, doc):
        return []


@pytest.fixture
def fake_spacy_backend(monkeypatch):
    """Replace TextTokenizer's spaCy pipeline with a small fake, in-place.

    Patches the names already bound inside app.services.package_text_tokenizer
    (``spacy`` and ``Matcher``), not the spacy package itself, so it has no
    effect outside that module.
    """
    import app.services.package_text_tokenizer as tokenizer_module

    monkeypatch.setattr(tokenizer_module.spacy, "load", lambda *a, **kw: _FakeNLP())
    monkeypatch.setattr(tokenizer_module, "Matcher", _FakeMatcher)
    yield
