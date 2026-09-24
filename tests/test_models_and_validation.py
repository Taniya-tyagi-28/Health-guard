"""
Unit tests for Machine Learning model prediction, feature validation,
and clinical intervention rules.
"""

import pytest
from ml.predictor import (
    validate_prediction_inputs,
    predict_adherence_risk,
    get_clinical_recommendations,
)


class TestInputValidation:
    """Tests feature boundary validation and type casting."""

    def test_valid_inputs_cast_correctly(self):
        inputs = validate_prediction_inputs(
            age="62",
            past_missed_doses="2",
            past_missed_appointments="1",
            treatment_duration_days="90",
            num_medications="4",
        )
        assert inputs == {
            "age": 62,
            "past_missed_doses": 2,
            "past_missed_appointments": 1,
            "treatment_duration_days": 90,
            "num_medications": 4,
        }

    def test_invalid_negative_missed_doses(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_prediction_inputs(
                age=50,
                past_missed_doses=-1,
                past_missed_appointments=0,
                treatment_duration_days=30,
                num_medications=2,
            )

    def test_invalid_negative_missed_appointments(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_prediction_inputs(
                age=50,
                past_missed_doses=0,
                past_missed_appointments=-2,
                treatment_duration_days=30,
                num_medications=2,
            )

    def test_invalid_age_bounds(self):
        with pytest.raises(ValueError, match="Age must be between 0 and 125"):
            validate_prediction_inputs(
                age=150,
                past_missed_doses=0,
                past_missed_appointments=0,
                treatment_duration_days=30,
                num_medications=1,
            )

        with pytest.raises(ValueError, match="Age must be between 0 and 125"):
            validate_prediction_inputs(
                age=-5,
                past_missed_doses=0,
                past_missed_appointments=0,
                treatment_duration_days=30,
                num_medications=1,
            )

    def test_invalid_zero_treatment_duration(self):
        with pytest.raises(ValueError, match="Treatment duration must be greater than 0"):
            validate_prediction_inputs(
                age=45,
                past_missed_doses=0,
                past_missed_appointments=0,
                treatment_duration_days=0,
                num_medications=1,
            )

    def test_invalid_zero_medications(self):
        with pytest.raises(ValueError, match="Number of medications must be at least 1"):
            validate_prediction_inputs(
                age=45,
                past_missed_doses=0,
                past_missed_appointments=0,
                treatment_duration_days=30,
                num_medications=0,
            )

    def test_non_numeric_input_raises_error(self):
        with pytest.raises(ValueError, match="must be numeric"):
            validate_prediction_inputs(
                age="fifty",
                past_missed_doses=0,
                past_missed_appointments=0,
                treatment_duration_days=30,
                num_medications=1,
            )


class TestModelPredictionLogic:
    """Tests Random Forest classification inference and risk scoring."""

    def test_prediction_output_structure(self):
        result = predict_adherence_risk(
            age=65,
            past_missed_doses=1,
            past_missed_appointments=0,
            treatment_duration_days=60,
            num_medications=3,
        )

        assert "risk_level" in result
        assert result["risk_level"] in ["Low", "Medium", "High"]
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 100.0
        assert "probabilities" in result
        assert set(result["probabilities"].keys()) == {"Low", "Medium", "High"}

        # Total probabilities should sum to approximately 1.0
        total_prob = sum(result["probabilities"].values())
        assert pytest.approx(total_prob, 0.01) == 1.0

        assert "recommendations" in result
        assert len(result["recommendations"]) > 10

    def test_high_risk_classification(self):
        # Patient with 8 missed doses and 3 missed appointments should classify as High risk
        result = predict_adherence_risk(
            age=72,
            past_missed_doses=8,
            past_missed_appointments=3,
            treatment_duration_days=180,
            num_medications=6,
        )
        assert result["risk_level"] == "High"
        assert result["probabilities"]["High"] > 0.60
        assert "outreach" in result["recommendations"].lower() or "sms" in result["recommendations"].lower()

    def test_low_risk_classification(self):
        # Patient with 0 missed doses, 0 missed visits, and simple regimen should classify as Low risk
        result = predict_adherence_risk(
            age=35,
            past_missed_doses=0,
            past_missed_appointments=0,
            treatment_duration_days=30,
            num_medications=1,
        )
        assert result["risk_level"] == "Low"
        assert result["probabilities"]["Low"] > 0.60
        assert "low risk" in result["recommendations"].lower()


class TestClinicalRecommendations:
    """Tests clinical recommendation text generation."""

    def test_high_risk_recommendation_includes_alerts(self):
        rec = get_clinical_recommendations("High", missed_doses=6, num_meds=7)
        assert "outreach" in rec.lower()
        assert "polypharmacy" in rec.lower() or "blister pack" in rec.lower()

    def test_medium_risk_recommendation(self):
        rec = get_clinical_recommendations("Medium", missed_doses=2, num_meds=3)
        assert "moderate risk" in rec.lower()

    def test_low_risk_recommendation(self):
        rec = get_clinical_recommendations("Low", missed_doses=0, num_meds=1)
        assert "low risk profile" in rec.lower()
