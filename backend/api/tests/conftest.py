"""Test bootstrap for the API test suite.

The API reads its configuration at import time: ``auth`` raises RuntimeError
when AUTH_PASSWORD is missing, and ``database`` binds the SQLAlchemy engine to
DB_PATH (default ``/data/makhal.db``). Force dummy values here, before pytest
imports any test module that imports ``main`` or ``database``, so tests run
from a clean environment and never touch the real database.
"""
import os
import tempfile

os.environ["AUTH_PASSWORD"] = "test-password"
os.environ["API_SECRET"] = "test-secret"
os.environ["HTTPS_ONLY"] = "false"
os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="makhal-reader-tests-"), "makhal-test.db"
)
