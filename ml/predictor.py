"""
Predictor inference module for HealthGuard.
Loads the trained Random Forest model and provides risk prediction, confidence scoring,
input validation, and clinical intervention recommendations.
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Union

MODEL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "healthguard_model.joblib")
)

_cached_model_bundle = None


def load_model():
    """Lazy loader for the serialized ML model bundle."""
    global _cached_model_bundle
    if _cached_model_bundle is None:
        if not os.path.exists(MODEL_PATH):
            # Fallback: train if model file does not exist
            from ml.train_model import train_and_export_model
            _cached_model_bundle = train_and_export_model(MODEL_PATH)
        else:
            _cached_model_bundle = joblib.load(MODEL_PATH)
    return _cached_model_bundle


def validate_prediction_inputs(
    age: Union[int, float],
    past_missed_doses: Union[int, float],
    past_missed_appointments: Union[int, float],
    treatment_duration_days: Union[int, float],
    num_medications: Union[int, float],
) -> Dict[str, Union[int, float]]:
    """
    Validates and casts the input features against clinical range limits.
    Raises ValueError with explanatory messages if invalid.
    """
    try:
        age = int(age)
        past_missed_doses = int(past_missed_doses)
        past_missed_appointments = int(past_missed_appointments)
        treatment_duration_days = int(treatment_duration_days)
        num_medications = int(num_medications)
    except (TypeError, ValueError) as e:
        raise ValueError(f"All features must be numeric integers. Error: {e}")

    if not (0 <= age <= 125):
        raise ValueError(f"Age must be between 0 and 125. Received: {age}")
    if past_missed_doses < 0:
        raise ValueError(f"Past missed doses cannot be negative. Received: {past_missed_doses}")
    if past_missed_appointments < 0:
        raise ValueError(f"Past missed appointments cannot be negative. Received: {past_missed_appointments}")
    if treatment_duration_days <= 0:
        raise ValueError(f"Treatment duration must be greater than 0. Received: {treatment_duration_days}")
    if num_medications <= 0:
        raise ValueError(f"Number of medications must be at least 1. Received: {num_medications}")

    return {
        "age": age,
        "past_missed_doses": past_missed_doses,
        "past_missed_appointments": past_missed_appointments,
        "treatment_duration_days": treatment_duration_days,
        "num_medications": num_medications,
    }


def get_clinical_recommendations(risk_level: str, missed_doses: int, num_meds: int) -> str:
    """Generates tailored intervention recommendations based on risk tier."""
    if risk_level == "High":
        recs = [
            "⚠️ Immediate clinical nurse outreach / telehealth follow-up required within 48h.",
            "Schedule automated daily SMS & phone call medication reminders.",
            "Conduct medication reconciliation review to simplify regimen.",
        ]
        if num_meds >= 5:
            recs.append("Recommend blister pack / pill organizer packaging due to polypharmacy.")
        return " ".join(recs)
    elif risk_level == "Medium":
        return (
            "⚠️ Moderate risk detected. Enable proactive push notifications. "
            "Send check-in survey 3 days prior to next scheduled appointment. "
            "Suggest patient utilizes the mobile intake tracker."
        )
    else:
        return (
            "✅ Low risk profile. Standard care protocol. Maintain current follow-up schedule "
            "and encourage continued adherence logging."
        )


def predict_adherence_risk(
    age: Union[int, float],
    past_missed_doses: Union[int, float],
    past_missed_appointments: Union[int, float],
    treatment_duration_days: Union[int, float],
    num_medications: Union[int, float],
) -> Dict[str, Any]:
    """
    Predicts medication adherence & follow-up miss risk for a patient.
    Returns:
        risk_level: 'Low' | 'Medium' | 'High'
        confidence: probability percentage for the predicted class
        probabilities: dict of class probabilities
        recommendations: clinical action text
        features: dictionary of input features
    """
    valid_features = validate_prediction_inputs(
        age=age,
        past_missed_doses=past_missed_doses,
        past_missed_appointments=past_missed_appointments,
        treatment_duration_days=treatment_duration_days,
        num_medications=num_medications,
    )

    bundle = load_model()
    model = bundle["model"]
    feature_names = bundle["feature_names"]

    # Build input DataFrame matching feature names used during training
    input_df = pd.DataFrame([{feat: valid_features[feat] for feat in feature_names}])

    prediction = model.predict(input_df)[0]
    probabilities_raw = model.predict_proba(input_df)[0]
    classes = list(model.classes_)

    probabilities = {
        cls: round(float(prob), 4) for cls, prob in zip(classes, probabilities_raw)
    }

    predicted_prob = probabilities.get(prediction, 0.0)

    recommendations = get_clinical_recommendations(
        risk_level=prediction,
        missed_doses=valid_features["past_missed_doses"],
        num_meds=valid_features["num_medications"],
    )

    return {
        "risk_level": prediction,
        "confidence": round(predicted_prob * 100, 2),
        "probabilities": probabilities,
        "recommendations": recommendations,
        "features": valid_features,
    }
