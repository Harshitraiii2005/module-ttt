"""API-level tests for /auth (app.api.auth), against a real temp SQLite DB.

Each test gets its own isolated database via the ``client`` fixture (see
tests/api/conftest.py -> tests/conftest.py), so signing up "alice" in one
test can never leak into another test's assertions.
"""


class TestSignup:
    def test_signup_creates_account_and_returns_201(self, client):
        response = client.post(
            "/auth/signup",
            json={"email": "new-user@example.com", "password": "S3cret-Pass!"},
        )
        assert response.status_code == 201
        assert response.json() == {"message": "Account created successfully"}

    def test_signup_duplicate_email_returns_409(self, client):
        payload = {"email": "dupe@example.com", "password": "S3cret-Pass!"}
        first = client.post("/auth/signup", json=payload)
        assert first.status_code == 201

        second = client.post("/auth/signup", json=payload)
        assert second.status_code == 409

    def test_signup_duplicate_email_is_case_insensitive(self, client):
        client.post(
            "/auth/signup",
            json={"email": "Case@Example.com", "password": "S3cret-Pass!"},
        )
        response = client.post(
            "/auth/signup",
            json={"email": "case@example.com", "password": "Another-Pass1!"},
        )
        assert response.status_code == 409


class TestLogin:
    def test_login_with_correct_credentials_returns_access_token(self, client):
        client.post(
            "/auth/signup",
            json={"email": "login-user@example.com", "password": "Correct-Pass1!"},
        )

        response = client.post(
            "/auth/login",
            json={"email": "login-user@example.com", "password": "Correct-Pass1!"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Successfully logged in"
        assert isinstance(body["access_token"], str) and body["access_token"]

    def test_login_with_wrong_password_returns_401(self, client):
        client.post(
            "/auth/signup",
            json={"email": "wrong-pass@example.com", "password": "Correct-Pass1!"},
        )

        response = client.post(
            "/auth/login",
            json={"email": "wrong-pass@example.com", "password": "Wrong-Pass1!"},
        )

        assert response.status_code == 401

    def test_login_with_unknown_email_returns_401(self, client):
        response = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "whatever"},
        )
        assert response.status_code == 401


class TestApiKeyCreation:
    def test_create_api_key_requires_bearer_token(self, client):
        response = client.post("/auth/api-keys")
        assert response.status_code in (401, 403)

    def test_create_api_key_with_valid_jwt_returns_key(self, client):
        client.post(
            "/auth/signup",
            json={"email": "keyholder@example.com", "password": "Correct-Pass1!"},
        )
        login = client.post(
            "/auth/login",
            json={"email": "keyholder@example.com", "password": "Correct-Pass1!"},
        )
        access_token = login.json()["access_token"]

        response = client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["api_key"].startswith("sk_")
        assert "created_at" in body

    def test_create_api_key_with_garbage_token_returns_401(self, client):
        response = client.post(
            "/auth/api-keys",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert response.status_code == 401

    def test_created_api_key_can_then_authenticate_other_routes(self, client):
        client.post(
            "/auth/signup",
            json={"email": "reuser@example.com", "password": "Correct-Pass1!"},
        )
        login = client.post(
            "/auth/login",
            json={"email": "reuser@example.com", "password": "Correct-Pass1!"},
        )
        access_token = login.json()["access_token"]
        key_response = client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        api_key = key_response.json()["api_key"]

        namespaces_response = client.get(
            "/v1/namespaces",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert namespaces_response.status_code == 200
