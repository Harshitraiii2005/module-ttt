"""Integration tests: talkingdb.helpers.namespace.store against a real,
on-disk SQLite database."""

import talkingdb.clients.sqlite as sqlite_client
from talkingdb.helpers.namespace import store as namespace_store


class TestEnsureReserved:
    def test_creates_the_demo_library_namespace(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespaces = namespace_store.list_namespaces(conn)
        names = {ns["namespace"] for ns in namespaces}
        assert "demo-library" in names

    def test_is_idempotent(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.ensure_reserved(conn)
            namespace_store.ensure_reserved(conn)
            namespaces = namespace_store.list_namespaces(conn)
        names = [ns["namespace"] for ns in namespaces]
        assert names.count("demo-library") == 1


class TestUpsertNamespace:
    def test_creates_a_new_namespace_with_given_fields(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(
                conn, "acme", title="Acme Corp", public_read=True
            )
            fetched = namespace_store.get_namespace(conn, "acme")

        assert fetched is not None
        assert fetched["title"] == "Acme Corp"
        assert fetched["public_read"] is True

    def test_upsert_on_existing_namespace_updates_fields(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "acme", title="Old", public_read=False)
            namespace_store.upsert_namespace(conn, "acme", title="New", public_read=True)
            fetched = namespace_store.get_namespace(conn, "acme")

        assert fetched["title"] == "New"
        assert fetched["public_read"] is True

    def test_get_unknown_namespace_returns_none(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            fetched = namespace_store.get_namespace(conn, "does-not-exist")
        assert fetched is None


class TestListNamespaces:
    def test_lists_every_created_namespace(self, initialized_db):
        with sqlite_client.sqlite_conn() as conn:
            namespace_store.upsert_namespace(conn, "one", public_read=True)
            namespace_store.upsert_namespace(conn, "two", public_read=False)
            names = {ns["namespace"] for ns in namespace_store.list_namespaces(conn)}

        assert {"one", "two", "demo-library"}.issubset(names)
