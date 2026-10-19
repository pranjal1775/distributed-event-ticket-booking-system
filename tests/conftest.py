import pytest


@pytest.fixture(autouse=True)
def isolate_test_jwt_secret(monkeypatch, request):
    """Tests share a process, but each service's test tokens use their own secret."""
    secret = (
        "test-secret-for-unit-tests-only-32chars"
        if request.module.__name__.endswith("test_users")
        else "test-secret-key"
    )
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
