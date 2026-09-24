"""
Database integrity and constraint tests for HealthGuard SQLite storage.
Verifies foreign key relationships, check constraints, cascade deletions,
and transactional persistence of prescriptions and prediction logs.
"""

import json
import sqlite3
import pytest
from database.db import get_db_connection


class TestDatabaseIntegrity:
    """Verifies relational integrity and constraints in SQLite schema."""

    def test_foreign_key_patient_doctor(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Non-existent doctor ID 9999 should violate FOREIGN KEY constraint
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO patients (doctor_id, name, age, gender, email)
                   VALUES (9999, 'Orphan Patient', 45, 'Male', 'orphan@test.com');"""
            )
        conn.close()

    def test_foreign_key_prescription_patient(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Non-existent patient ID 8888 should violate FOREIGN KEY constraint
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO prescriptions 
                   (patient_id, doctor_id, medication_name, dosage, frequency, start_date, treatment_duration_days)
                   VALUES (8888, 1, 'Aspirin', '81mg', 'Daily', '2026-01-01', 30);"""
            )
        conn.close()

    def test_check_constraint_patient_age(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Age > 125 violates CHECK(age >= 0 AND age <= 125)
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO patients (doctor_id, name, age, gender, email)
                   VALUES (1, 'Supercentenarian', 150, 'Female', 'old@test.com');"""
            )

        # Negative age violates CHECK(age >= 0)
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO patients (doctor_id, name, age, gender, email)
                   VALUES (1, 'Negative Age', -3, 'Female', 'neg@test.com');"""
            )
        conn.close()

    def test_check_constraint_treatment_duration(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Treatment duration <= 0 violates CHECK(treatment_duration_days > 0)
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO prescriptions 
                   (patient_id, doctor_id, medication_name, dosage, frequency, start_date, treatment_duration_days)
                   VALUES (1, 1, 'Amoxicillin', '500mg', 'Twice daily', '2026-01-01', 0);"""
            )
        conn.close()

    def test_check_constraint_prescription_status(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Invalid status violates CHECK(status IN ('Active', 'Completed', 'Discontinued'))
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                """INSERT INTO prescriptions 
                   (patient_id, doctor_id, medication_name, dosage, frequency, start_date, treatment_duration_days, status)
                   VALUES (1, 1, 'Ibuprofen', '400mg', 'As needed', '2026-01-01', 14, 'PendingApproval');"""
            )
        conn.close()

    def test_cascade_delete_patient(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Verify initial records for patient 1
        cur.execute("SELECT COUNT(*) FROM prescriptions WHERE patient_id = 1;")
        assert cur.fetchone()[0] >= 1

        cur.execute("SELECT COUNT(*) FROM adherence_logs WHERE patient_id = 1;")
        assert cur.fetchone()[0] >= 1

        # Delete patient 1
        cur.execute("DELETE FROM patients WHERE id = 1;")
        conn.commit()

        # Cascading deletion should have purged patient 1's prescriptions and logs
        cur.execute("SELECT COUNT(*) FROM prescriptions WHERE patient_id = 1;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM adherence_logs WHERE patient_id = 1;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM risk_assessments WHERE patient_id = 1;")
        assert cur.fetchone()[0] == 0
        conn.close()

    def test_prescription_storage_and_prediction_logs_integrity(self, test_db):
        conn = get_db_connection(test_db)
        cur = conn.cursor()

        # Store a new prescription
        cur.execute(
            """INSERT INTO prescriptions 
               (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, treatment_duration_days, status)
               VALUES (2, 1, 'Atorvastatin', '20mg', 'Once daily', 'Take with water', '2026-02-01', 90, 'Active');"""
        )
        rx_id = cur.lastrowid
        assert rx_id is not None

        # Verify prescription retrieval
        cur.execute("SELECT * FROM prescriptions WHERE id = ?;", (rx_id,))
        rx = dict(cur.fetchone())
        assert rx["medication_name"] == "Atorvastatin"
        assert rx["dosage"] == "20mg"
        assert rx["treatment_duration_days"] == 90

        # Store risk assessment log
        features = {
            "age": 42,
            "past_missed_doses": 0,
            "past_missed_appointments": 0,
            "treatment_duration_days": 90,
            "num_medications": 2,
        }
        cur.execute(
            """INSERT INTO risk_assessments 
               (patient_id, risk_level, risk_score, features_json, recommendations)
               VALUES (2, 'Low', 98.2, ?, 'Continue regimen');""",
            (json.dumps(features),),
        )
        assessment_id = cur.lastrowid
        assert assessment_id is not None

        # Query and verify JSON integrity
        cur.execute("SELECT * FROM risk_assessments WHERE id = ?;", (assessment_id,))
        log_entry = dict(cur.fetchone())
        assert log_entry["risk_level"] == "Low"
        assert log_entry["risk_score"] == 98.2
        parsed_features = json.loads(log_entry["features_json"])
        assert parsed_features["age"] == 42
        assert parsed_features["num_medications"] == 2

        conn.close()
