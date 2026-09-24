"""
API endpoint tests for HealthGuard platform.
Tests Patient API, Prediction API, Prescription API, Adherence API, and Analytics API.
"""

import json
import pytest


class TestPredictionApi:
    """Tests for POST /api/predict"""

    def test_predict_success(self, client):
        payload = {
            "age": 68,
            "past_missed_doses": 5,
            "past_missed_appointments": 2,
            "treatment_duration_days": 90,
            "num_medications": 4,
        }
        res = client.post(
            "/api/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "prediction" in data
        assert data["prediction"]["risk_level"] in ["Low", "Medium", "High"]
        assert "confidence" in data["prediction"]
        assert "recommendations" in data["prediction"]

    def test_predict_missing_fields(self, client):
        payload = {"age": 50}  # Missing other required features
        res = client.post(
            "/api/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 400
        data = res.get_json()
        assert "Missing required feature keys" in data["error"]

    def test_predict_invalid_data_ranges(self, client):
        payload = {
            "age": 200,  # Invalid age
            "past_missed_doses": 0,
            "past_missed_appointments": 0,
            "treatment_duration_days": 30,
            "num_medications": 1,
        }
        res = client.post(
            "/api/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 422
        assert "Age must be between" in res.get_json()["error"]

    def test_predict_with_patient_id_persists_log(self, client):
        payload = {
            "patient_id": 1,
            "age": 55,
            "past_missed_doses": 2,
            "past_missed_appointments": 1,
            "treatment_duration_days": 60,
            "num_medications": 2,
        }
        res = client.post(
            "/api/predict",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"


class TestPatientApi:
    """Tests for GET /api/patients and GET /api/patients/<id>"""

    def test_get_patients_list(self, client):
        res = client.get("/api/patients")
        assert res.status_code == 200
        data = res.get_json()
        assert "patients" in data
        assert data["count"] >= 2
        # Verify adherence rate calculation exists
        assert "adherence_rate" in data["patients"][0]

    def test_get_patient_detail_success(self, client):
        res = client.get("/api/patients/1")
        assert res.status_code == 200
        data = res.get_json()
        assert data["patient"]["name"] == "John Doe"
        assert "prescriptions" in data
        assert "recent_adherence_logs" in data
        assert "adherence_statistics" in data
        assert data["adherence_statistics"]["total"] == 2

    def test_get_patient_detail_not_found(self, client):
        res = client.get("/api/patients/9999")
        assert res.status_code == 404
        assert "not found" in res.get_json()["error"].lower()


class TestPrescriptionApi:
    """Tests for POST /api/prescriptions and PUT /api/prescriptions/<id>"""

    def test_create_prescription_success(self, client):
        payload = {
            "patient_id": 1,
            "doctor_id": 1,
            "medication_name": "Metformin",
            "dosage": "500mg",
            "frequency": "Twice daily",
            "instructions": "Take with meals",
            "treatment_duration_days": 60,
        }
        res = client.post(
            "/api/prescriptions",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "success"
        assert "prescription_id" in data
        assert "updated_risk" in data

    def test_create_prescription_missing_field(self, client):
        payload = {
            "patient_id": 1,
            "doctor_id": 1,
            # Missing medication_name, dosage, frequency
        }
        res = client.post(
            "/api/prescriptions",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_create_prescription_non_existent_patient(self, client):
        payload = {
            "patient_id": 9999,
            "doctor_id": 1,
            "medication_name": "Metformin",
            "dosage": "500mg",
            "frequency": "Once daily",
            "treatment_duration_days": 30,
        }
        res = client.post(
            "/api/prescriptions",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 404

    def test_update_prescription_status(self, client):
        res = client.put(
            "/api/prescriptions/1",
            data=json.dumps({"status": "Completed"}),
            content_type="application/json",
        )
        assert res.status_code == 200
        assert "Completed" in res.get_json()["message"]

    def test_update_prescription_invalid_status(self, client):
        res = client.put(
            "/api/prescriptions/1",
            data=json.dumps({"status": "InvalidStatus"}),
            content_type="application/json",
        )
        assert res.status_code == 400


class TestAdherenceApi:
    """Tests for POST /api/adherence"""

    def test_log_adherence_success(self, client):
        payload = {
            "prescription_id": 1,
            "patient_id": 1,
            "status": "Taken",
            "notes": "Taken with breakfast",
        }
        res = client.post(
            "/api/adherence",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "success"
        assert "log_id" in data
        assert "latest_risk" in data

    def test_log_adherence_invalid_status(self, client):
        payload = {
            "prescription_id": 1,
            "patient_id": 1,
            "status": "SkippedMaybe",
        }
        res = client.post(
            "/api/adherence",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 400
        assert "status must be one of" in res.get_json()["error"]

    def test_log_adherence_prescription_patient_mismatch(self, client):
        # Prescription 1 belongs to patient 1, not patient 2
        payload = {
            "prescription_id": 1,
            "patient_id": 2,
            "status": "Taken",
        }
        res = client.post(
            "/api/adherence",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert res.status_code == 400
        assert "does not belong" in res.get_json()["error"]


class TestAnalyticsApi:
    """Tests for GET /api/analytics"""

    def test_get_analytics_summary(self, client):
        res = client.get("/api/analytics")
        assert res.status_code == 200
        data = res.get_json()

        assert "kpis" in data
        assert data["kpis"]["total_patients"] >= 2
        assert "overall_adherence_rate" in data["kpis"]
        assert "risk_distribution" in data
        assert "adherence_trend" in data
        assert "high_risk_patients" in data
