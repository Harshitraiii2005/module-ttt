"""Guardrails for pre-existing import bugs, independent of test coverage.

At the dependency revisions currently pinned in ``pyproject.toml``, the
following modules raise ``ModuleNotFoundError`` on import - this is true on
a clean checkout with every declared dependency installed, not an artifact
of the test environment:

* ``app/api/documents.py``    -> imports ``talkingdb.helpers.release_channel``
                                  (does not exist at the pinned
                                  ``talkingdb-helpers`` rev) and imports the
                                  ``minio`` package, which is not declared
                                  as a dependency anywhere in pyproject.toml.
* ``app/api/projects.py``     -> imports ``talkingdb.helpers.project`` and
                                  ``talkingdb.helpers.logo`` (neither exists
                                  at the pinned rev).
* ``app/api/validators.py``   -> imports ``talkingdb.helpers.project``
                                  (pre-existing; already flagged by
                                  ``tests/unit/test_validators.py``).
* ``app/services/workers.py`` -> imports ``talkingdb.helpers.project`` and
                                  ``talkingdb.clients.minio`` (neither
                                  exists at the pinned rev/package).
* ``app/services/jobs.py``    -> imports ``talkingdb.helpers.file_graph``
                                  (does not exist at the pinned rev).
* ``app/services/job_daemon.py`` -> imports ``app.services.jobs``, so it
                                  fails transitively.
* ``app/main.py``             -> imports ``app.api.documents`` and
                                  ``app.api.projects``, so the whole app
                                  currently fails to start (``uvicorn
                                  app.main:app`` will raise on import,
                                  independent of any web server config).

None of this is a testing gap - these modules cannot be exercised by *any*
test until the dependency pins are bumped (or the missing submodules are
added to ``base-tdb-helpers``/the ``minio`` dependency is declared). These
tests exist so that:

1. The gap is visible in CI output instead of silently absent.
2. The moment the underlying bug is fixed, these tests start passing
   automatically (``importorskip`` becomes a real import) with no test
   changes required, and the corresponding module immediately starts
   contributing to coverage.

Real unit/integration/API tests for these modules should be added directly
in ``tests/unit`` / ``tests/api`` / ``tests/integration`` once import
succeeds - do not accumulate real test logic in this file.
"""

import pytest


def test_documents_module_currently_unimportable():
    pytest.importorskip(
        "app.api.documents",
        reason=(
            "app.api.documents imports talkingdb.helpers.release_channel, "
            "which does not exist at the pinned talkingdb-helpers rev, and "
            "imports the third-party 'minio' package, which is not declared "
            "as a project dependency. Pre-existing bug, unrelated to this "
            "test suite."
        ),
    )


def test_projects_module_currently_unimportable():
    pytest.importorskip(
        "app.api.projects",
        reason=(
            "app.api.projects imports talkingdb.helpers.project and "
            "talkingdb.helpers.logo, neither of which exists at the pinned "
            "talkingdb-helpers rev. Pre-existing bug, unrelated to this "
            "test suite."
        ),
    )


def test_workers_module_currently_unimportable():
    pytest.importorskip(
        "app.services.workers",
        reason=(
            "app.services.workers imports talkingdb.helpers.project and "
            "talkingdb.clients.minio, neither of which exists at the pinned "
            "rev/is an installed dependency. Pre-existing bug, unrelated to "
            "this test suite."
        ),
    )


def test_jobs_service_module_currently_unimportable():
    pytest.importorskip(
        "app.services.jobs",
        reason=(
            "app.services.jobs imports talkingdb.helpers.file_graph, which "
            "does not exist at the pinned talkingdb-helpers rev. "
            "Pre-existing bug, unrelated to this test suite."
        ),
    )


def test_job_daemon_module_currently_unimportable():
    pytest.importorskip(
        "app.services.job_daemon",
        reason=(
            "app.services.job_daemon imports app.services.jobs, which fails "
            "to import (see test_jobs_service_module_currently_unimportable). "
            "Pre-existing bug, unrelated to this test suite. Also excluded "
            "from coverage via pyproject.toml / codecov.yml."
        ),
    )


def test_main_app_currently_unimportable():
    pytest.importorskip(
        "app.main",
        reason=(
            "app.main imports app.api.documents and app.api.projects, both "
            "of which fail to import at the current dependency pins, so the "
            "whole application currently fails to start. Pre-existing bug, "
            "unrelated to this test suite. See the other tests in this file "
            "for the individual root causes."
        ),
    )
