import os
from pathlib import Path
import shutil
import tempfile


_TEST_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="ppg-rag-tests-"))
# Never inherit the checked-out deployment's APP_ENV.  The production
# launcher uses ``internal`` and correctly rejects auth bypass; the suite uses
# an isolated database plus explicit test-only overrides below.
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_DATABASE_URL"] = f"sqlite:///{_TEST_RUNTIME_DIR / 'admin.db'}"
os.environ["ADMIN_LOCK_DIR"] = str(_TEST_RUNTIME_DIR / "locks")
os.environ.setdefault("REPORT_MODE", "template_only")
os.environ.setdefault("LLM_PROVIDER", "mock")
# Tests stay offline-deterministic even when an embedding API key is
# configured in .env: pin the retrieval vector backend to hashing.
os.environ.setdefault("RETRIEVAL_EMBEDDING_BACKEND", "hashing")
# The deployment shell may export the production values. Force legacy route
# tests into their documented isolated mode; security tests explicitly switch
# authentication back on against the temporary Admin DB.
os.environ["ADMIN_AUTH_DISABLED"] = "1"
os.environ["REQUIRE_API_CLIENT"] = "0"


def pytest_sessionfinish(session, exitstatus):
    del session, exitstatus
    shutil.rmtree(_TEST_RUNTIME_DIR, ignore_errors=True)
