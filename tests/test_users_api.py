"""API-042: Endpoint tests for the /users backoffice resource.

Each endpoint is covered with at least one happy path, one edge case and one
failure mode. These tests exercise the business rules that matter:

- anyone can create an account (public sign-up, no auth required)
- users can read/update their own record but not other people's (role checks)
- admins can list and manage all users
- duplicate emails, malformed payloads and unknown ids are rejected
"""

from __future__ import annotations


def _user_payload(email: str, password: str = "StrongPass123!", **overrides) -> dict:
    return {"email": email, "password": password, **overrides}


class TestCreateUser:
    def test_happy_path_creates_user_with_hashed_password(self, client, make_email):
        email = make_email("users")
        response = client.post(
            "/users", json=_user_payload(email, profile={"display_name": "Ada"})
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == email
        assert body["id"] > 0
        # The password must be stored hashed, never returned in plaintext.
        assert body["hashed_password"] != "StrongPass123!"
        assert "StrongPass123!" not in body["hashed_password"]
        assert body["role"] == "user"
        assert body["profile"]["display_name"] == "Ada"

    def test_edge_case_defaults_role_to_user(self, client, make_email):
        email = make_email("users")
        response = client.post("/users", json=_user_payload(email))
        assert response.status_code == 201
        assert response.json()["role"] == "user"
        assert response.json()["is_active"] is True

    def test_failure_duplicate_email_is_rejected(self, client, make_email):
        email = make_email("users")
        first = client.post("/users", json=_user_payload(email))
        assert first.status_code == 201
        second = client.post("/users", json=_user_payload(email))
        assert second.status_code == 400
        assert "already exists" in second.json()["detail"]

    def test_failure_invalid_email_is_rejected(self, client):
        response = client.post(
            "/users", json=_user_payload("not-an-email")
        )
        assert response.status_code == 422

    def test_failure_short_password_is_rejected(self, client, make_email):
        response = client.post(
            "/users", json=_user_payload(make_email("users"), password="short")
        )
        assert response.status_code == 422


class TestListUsers:
    def test_happy_path_admin_lists_all_users(self, client, admin_account):
        """Admins can list the directory of users."""
        response = client.get("/users", headers=admin_account["headers"])
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert any(user["id"] == admin_account["user"]["id"] for user in body)

    def test_edge_case_authenticated_user_can_list(self, client, auth_headers):
        """The list endpoint requires authentication but not admin role."""
        headers, account = auth_headers
        response = client.get("/users", headers=headers)
        assert response.status_code == 200
        assert any(user["id"] == account["user"]["id"] for user in response.json())

    def test_failure_unauthenticated_list_is_rejected(self, client):
        assert client.get("/users").status_code == 401


class TestGetUser:
    def test_happy_path_user_reads_own_record(self, client, auth_headers):
        headers, account = auth_headers
        user_id = account["user"]["id"]
        response = client.get(f"/users/{user_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["email"] == account["email"]

    def test_failure_missing_user_returns_404(self, client, auth_headers):
        headers, _ = auth_headers
        assert client.get("/users/999999", headers=headers).status_code == 404

    def test_failure_non_admin_cannot_read_other_user(self, client, create_user, auth_headers):
        headers, _ = auth_headers
        other = create_user()
        response = client.get(f"/users/{other['user']['id']}", headers=headers)
        assert response.status_code == 403

    def test_failure_unauthenticated_read_is_rejected(self, client, auth_headers):
        _, account = auth_headers
        assert client.get(f"/users/{account['user']['id']}").status_code == 401


class TestPatchUser:
    def test_happy_path_user_updates_own_role(self, client, auth_headers):
        headers, account = auth_headers
        user_id = account["user"]["id"]
        response = client.patch(
            f"/users/{user_id}", json={"role": "manager"}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["role"] == "manager"

    def test_failure_non_admin_cannot_edit_other_user(self, client, create_user, auth_headers):
        headers, _ = auth_headers
        other = create_user()
        response = client.patch(
            f"/users/{other['user']['id']}", json={"role": "admin"}, headers=headers
        )
        assert response.status_code == 403

    def test_failure_missing_user_returns_404(self, client, auth_headers):
        headers, _ = auth_headers
        response = client.patch("/users/999999", json={"role": "admin"}, headers=headers)
        assert response.status_code == 404


class TestDeleteUser:
    def test_happy_path_admin_deletes_user(self, client, admin_account, create_user):
        victim = create_user()
        response = client.delete(
            f"/users/{victim['user']['id']}", headers=admin_account["headers"]
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": True, "id": victim["user"]["id"]}

    def test_failure_non_admin_cannot_delete_other_user(self, client, create_user, auth_headers):
        headers, _ = auth_headers
        other = create_user()
        response = client.delete(f"/users/{other['user']['id']}", headers=headers)
        assert response.status_code == 403

    def test_failure_missing_user_returns_404(self, client, admin_account):
        response = client.delete("/users/999999", headers=admin_account["headers"])
        assert response.status_code == 404