"""
Authentication and Login Portal Tests for HealthGuard.
Tests user authentication, password hashing, role-based redirection,
session management, registration, and UI endpoint responses.
"""

import pytest
from app.auth import authenticate_user, register_new_user, ensure_auth_tables


class TestAuthenticationUnit:
    """Unit tests for the authentication and password verification helpers."""

    def test_default_users_seeded(self, test_db):
        ensure_auth_tables(test_db)
        
        # Verify doctor authentication
        doc = authenticate_user("s.jenkins@healthguard.org", "doctor123", db_path=test_db)
        assert doc is not None
        assert doc["role"] == "doctor"
        assert doc["doctor_id"] == 1

        # Verify patient authentication
        pat = authenticate_user("arthur.p@example.com", "patient123", db_path=test_db)
        assert pat is not None
        assert pat["role"] == "patient"
        assert pat["patient_id"] == 1

        # Verify admin authentication
        adm = authenticate_user("admin@healthguard.org", "admin123", db_path=test_db)
        assert adm is not None
        assert adm["role"] == "admin"

    def test_authenticate_invalid_password(self, test_db):
        ensure_auth_tables(test_db)
        user = authenticate_user("admin@healthguard.org", "wrongpassword", db_path=test_db)
        assert user is None

    def test_authenticate_nonexistent_user(self, test_db):
        ensure_auth_tables(test_db)
        user = authenticate_user("nonexistent@example.com", "password123", db_path=test_db)
        assert user is None

    def test_register_patient(self, test_db):
        ensure_auth_tables(test_db)
        new_pat = register_new_user(
            username="newpatient",
            email="newpatient@test.com",
            password="securepassword123",
            role="patient",
            full_name="New Patient Test",
            extra_field="42",
            db_path=test_db,
        )
        assert new_pat["role"] == "patient"
        assert new_pat["patient_id"] is not None

        # Verify login with new patient credentials
        login_res = authenticate_user("newpatient@test.com", "securepassword123", db_path=test_db)
        assert login_res is not None
        assert login_res["username"] == "newpatient"

    def test_register_doctor(self, test_db):
        ensure_auth_tables(test_db)
        new_doc = register_new_user(
            username="dr.newdoc",
            email="newdoc@hospital.org",
            password="securepassword123",
            role="doctor",
            full_name="Dr. New Doctor",
            extra_field="Oncology",
            db_path=test_db,
        )
        assert new_doc["role"] == "doctor"
        assert new_doc["doctor_id"] is not None

        # Verify login
        login_res = authenticate_user("dr.newdoc", "securepassword123", db_path=test_db)
        assert login_res is not None
        assert login_res["role"] == "doctor"


class TestLoginRoutes:
    """HTTP integration tests for /login, /register, and /logout."""

    def test_get_login_page(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.get("/login")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Welcome to HealthGuard" in html
        assert "loginIdentifier" in html
        assert "loginPassword" in html
        assert "demoDoctorBtn" in html
        assert "demoPatientBtn" in html
        assert "demoAdminBtn" in html

    def test_post_login_doctor_success(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.post(
            "/login",
            data={
                "identifier": "s.jenkins@healthguard.org",
                "password": "doctor123",
                "role": "doctor",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert "/doctor/" in res.headers["Location"]

        # Check session
        with client.session_transaction() as sess:
            assert sess["role"] == "doctor"
            assert sess["username"] == "dr.jenkins"

    def test_post_login_patient_success(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.post(
            "/login",
            data={
                "identifier": "arthur.p@example.com",
                "password": "patient123",
                "role": "patient",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert "/patient/" in res.headers["Location"]

        with client.session_transaction() as sess:
            assert sess["role"] == "patient"
            assert sess["username"] == "arthur.p"

    def test_post_login_admin_success(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.post(
            "/login",
            data={
                "identifier": "admin@healthguard.org",
                "password": "admin123",
                "role": "admin",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert "/admin" in res.headers["Location"]

        with client.session_transaction() as sess:
            assert sess["role"] == "admin"
            assert sess["username"] == "admin"

    def test_post_login_invalid_credentials(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.post(
            "/login",
            data={
                "identifier": "admin@healthguard.org",
                "password": "badpassword",
            },
            follow_redirects=True,
        )
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Invalid clinical credentials" in html

    def test_logout(self, client, test_db):
        ensure_auth_tables(test_db)
        # Login first
        client.post(
            "/login",
            data={"identifier": "admin@healthguard.org", "password": "admin123"},
        )
        # Logout
        res = client.get("/logout", follow_redirects=False)
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_root_redirects_unauthenticated_to_login(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_root_redirects_authenticated_doctor(self, client, test_db):
        ensure_auth_tables(test_db)
        # Sign in as doctor
        client.post("/login", data={"identifier": "s.jenkins@healthguard.org", "password": "doctor123", "role": "doctor"})
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 302
        assert "/doctor/" in res.headers["Location"]

    def test_overview_page_accessible(self, client, test_db):
        ensure_auth_tables(test_db)
        res = client.get("/overview")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Predictive Patient Follow-Up" in html

