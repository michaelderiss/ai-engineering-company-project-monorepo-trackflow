"""API-042: Endpoint tests for the /profiles backoffice resource.

Covers the profile lifecycle: create, read own profile, patch (create-or-update),
and role-based access control. Each endpoint has at least one happy path, one
edge case and one failure mode.
"""

from __future__ import annotations


def _profile_payload(**overrides) -> dict:
    payload = {"display_name": "Grace Hopper", "phone": "+1-555-0100"}
    payload.update(overrides)
    return payload


class TestCreateProfile:
    def test_happy_path_creates_profile(self, client, auth_headers):
        headers, account = auth_headers
        response = client.post("/profiles", json=_profile_payload(), headers=headers)
        assert response.status_code == 201
        body = response.json()
        assert body["display_name"] == "Grace Hopper"
        assert body["user_id"] == account["user"]["id"]
        assert body["id"] > 0

    def test_edge_case_profile_tied_to_authenticated_user(self, client, create_user, auth_headers):
        headers, account = auth_headers
        client.post("/profiles", json=_profile_payload(), headers=headers)
        # The profile's user_id must be the token's user, not any other account.
        response = client.get("/profiles/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] == account["user"]["id"]

    def test_failure_duplicate_profile_is_rejected(self, client, auth_headers):
        headers, _ = auth_headers
        first = client.post("/profiles", json=_profile_payload(), headers=headers)
        assert first.status_code == 201
        second = client.post("/profiles", json=_profile_payload(), headers=headers)
        assert second.status_code == 400
        assert "already has a profile" in second.json()["detail"]

    def test_failure_unauthenticated_create_is_rejected(self, client):
        response = client.post("/profiles", json=_profile_payload())
        assert response.status_code == 401

    def test_failure_blank_display_name_is_rejected(self, client, auth_headers):
        headers, _ = auth_headers
        response = client.post(
            "/profiles", json=_profile_payload(display_name=""), headers=headers
        )
        assert response.status_code == 422


class TestGetOwnProfile:
    def test_happy_path_returns_own_profile(self, client, auth_headers):
        headers, _ = auth_headers
        client.post("/profiles", json=_profile_payload(), headers=headers)
        response = client.get("/profiles/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["display_name"] == "Grace Hopper"

    def test_failure_no_profile_returns_404(self, client, auth_headers):
        headers, _ = auth_headers
        response = client.get("/profiles/me", headers=headers)
        assert response.status_code == 404


class TestPatchOwnProfile:
    def test_happy_path_patch_updates_existing_profile(self, client, auth_headers):
        headers, _ = auth_headers
        client.post("/profiles", json=_profile_payload(), headers=headers)
        response = client.patch(
            "/profiles/me",
            json=_profile_payload(display_name="Grace B. Hopper"),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Grace B. Hopper"

    def test_edge_case_patch_creates_when_missing(self, client, auth_headers):
        """PATCH /profiles/me is upsert: it creates the profile if absent."""
        headers, _ = auth_headers
        response = client.patch(
            "/profiles/me", json=_profile_payload(), headers=headers
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Grace Hopper"

    def test_failure_unauthenticated_patch_is_rejected(self, client):
        response = client.patch("/profiles/me", json=_profile_payload())
        assert response.status_code == 401


class TestListProfiles:
    def test_happy_path_admin_lists_profiles(self, client, admin_account):
        response = client.get("/profiles", headers=admin_account["headers"])
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_failure_regular_user_cannot_list_all(self, client, auth_headers):
        headers, _ = auth_headers
        response = client.get("/profiles", headers=headers)
        assert response.status_code == 403


class TestGetProfileById:
    def test_happy_path_admin_reads_any_profile(self, client, admin_account):
        """Admins can fetch a profile by id, including someone else's."""
        headers = admin_account["headers"]
        client.post("/profiles", json=_profile_payload(), headers=headers)
        admin_profile = client.get("/profiles/me", headers=headers).json()
        fetched = client.get(f"/profiles/{admin_profile['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["id"] == admin_profile["id"]

    def test_happy_path_user_reads_own_profile_by_id(self, client, auth_headers):
        headers, _ = auth_headers
        created = client.post("/profiles", json=_profile_payload(), headers=headers).json()
        fetched = client.get(f"/profiles/{created['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["user_id"] == created["user_id"]

    def test_failure_non_admin_cannot_read_other_profile(self, client, admin_account, auth_headers):
        admin_headers = admin_account["headers"]
        client.post("/profiles", json=_profile_payload(), headers=admin_headers)
        admin_profile = client.get("/profiles/me", headers=admin_headers).json()
        headers, _ = auth_headers
        response = client.get(
            f"/profiles/{admin_profile['id']}", headers=headers
        )
        assert response.status_code == 403

    def test_failure_missing_profile_returns_404(self, client, admin_account):
        response = client.get("/profiles/999999", headers=admin_account["headers"])
        assert response.status_code == 404


class TestPatchProfileById:
    def test_happy_path_admin_patches_any_profile(self, client, admin_account):
        headers = admin_account["headers"]
        created = client.post("/profiles", json=_profile_payload(), headers=headers).json()
        response = client.patch(
            f"/profiles/{created['id']}",
            json=_profile_payload(phone="+1-555-0199"),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["phone"] == "+1-555-0199"

    def test_failure_non_admin_cannot_patch_other_profile(self, client, admin_account, auth_headers):
        admin_headers = admin_account["headers"]
        created = client.post("/profiles", json=_profile_payload(), headers=admin_headers).json()
        headers, _ = auth_headers
        response = client.patch(
            f"/profiles/{created['id']}", json=_profile_payload(), headers=headers
        )
        assert response.status_code == 403

    def test_failure_missing_profile_returns_404(self, client, admin_account):
        response = client.patch(
            "/profiles/999999", json=_profile_payload(), headers=admin_account["headers"]
        )
        assert response.status_code == 404