"""
Pytest configuration and shared test fixtures for HealthGuard.
Creates isolated temporary databases and a configured Flask test client.
"""

import os
import sys
import tempfile
import sqlite3
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import init_db, get_db_connection
from app import create_app


@pytest.fixture(scope="function")
def test_db():
    """
    Creates a temporary SQLite database file for testing, initializes tables,
    and seeds a deterministic baseline of doctors, patients, and prescriptions.
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    # Initialize schema
    init_db(db_path)

    # Seed baseline records
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Doctor
    cur.execute(
        "INSERT INTO doctors (id, name, specialty, email, phone) VALUES (1, 'Dr. Alice Reed', 'Cardiology', 'a.reed@test.org', '+1-555-9999');"
    )

    # Patients
    cur.execute(
        """INSERT INTO patients (id, doctor_id, name, age, gender, phone, email, chronic_conditions)
           VALUES (1, 1, 'John Doe', 55, 'Male', '+1-555-0001', 'john.doe@test.org', 'Hypertension');"""
    )
    cur.execute(
        """INSERT INTO patients (id, doctor_id, name, age, gender, phone, email, chronic_conditions)
           VALUES (2, 1, 'Jane Smith', 42, 'Female', '+1-555-0002', 'jane.smith@test.org', 'Asthma');"""
    )

    # Prescriptions
    cur.execute(
        """INSERT INTO prescriptions (id, patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, end_date, treatment_duration_days, status)
           VALUES (1, 1, 1, 'Lisinopril', '10mg', 'Once daily', 'Take in morning', '2026-01-01', '2026-03-31', 90, 'Active');"""
    )
    cur.execute(
        """INSERT INTO prescriptions (id, patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, end_date, treatment_duration_days, status)
           VALUES (2, 2, 1, 'Albuterol', '90mcg', 'As needed', 'Inhale 2 puffs', '2026-01-01', '2026-01-31', 30, 'Active');"""
    )

    # Initial adherence logs
    cur.execute(
        """INSERT INTO adherence_logs (id, prescription_id, patient_id, scheduled_time, logged_time, status, notes)
           VALUES (1, 1, 1, '2026-01-02 08:00:00', '2026-01-02 08:05:00', 'Taken', 'On time');"""
    )
    cur.execute(
        """INSERT INTO adherence_logs (id, prescription_id, patient_id, scheduled_time, logged_time, status, notes)
           VALUES (2, 1, 1, '2026-01-03 08:00:00', '2026-01-03 08:10:00', 'Missed', 'Forgot dose');"""
    )

    # Risk Assessment
    cur.execute(
        """INSERT INTO risk_assessments (id, patient_id, risk_level, risk_score, features_json, recommendations)
           VALUES (1, 1, 'Low', 94.5, '{"age": 55, "past_missed_doses": 1}', 'Routine care');"""
    )

    conn.commit()
    conn.close()

    # Set environment variable so application routes pick up the test DB
    old_env = os.environ.get("HEALTHGUARD_DB_PATH")
    os.environ["HEALTHGUARD_DB_PATH"] = db_path

    yield db_path

    # Teardown
    if old_env is not None:
        os.environ["HEALTHGUARD_DB_PATH"] = old_env
    else:
        os.environ.pop("HEALTHGUARD_DB_PATH", None)

    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def client(test_db):
    """
    Flask test client fixture configured with the isolated temporary test database.
    """
    flask_app = create_app(
        {
            "TESTING": True,
            "DATABASE": test_db,
            "SECRET_KEY": "test-secret-key",
        }
    )

    with flask_app.test_client() as test_client:
        with flask_app.app_context():
            yield test_client
