import os


os.environ.setdefault("REPORT_MODE", "template_only")
os.environ.setdefault("LLM_PROVIDER", "mock")
# Tests stay offline-deterministic even when an embedding API key is
# configured in .env: pin the retrieval vector backend to hashing.
os.environ.setdefault("RETRIEVAL_EMBEDDING_BACKEND", "hashing")
# Legacy API tests exercise route behavior rather than authentication. Security
# tests explicitly switch this back on with an isolated admin database.
os.environ.setdefault("ADMIN_AUTH_DISABLED", "1")
os.environ.setdefault("REQUIRE_API_CLIENT", "0")
