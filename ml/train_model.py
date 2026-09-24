"""
Machine Learning Training Pipeline for HealthGuard.
Trains a RandomForestClassifier to predict patient non-adherence & appointment miss risk (Low, Medium, High).
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split

MODEL_OUTPUT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "healthguard_model.joblib")
)

FEATURE_NAMES = [
    "age",
    "past_missed_doses",
    "past_missed_appointments",
    "treatment_duration_days",
    "num_medications",
]


def generate_synthetic_data(n_samples: int = 5000, random_seed: int = 42) -> pd.DataFrame:
    """
    Generates a realistic clinical dataset modeling medication non-adherence
    and missed appointments with a balanced, clinically-grounded distribution
    across Low, Medium, and High risk tiers.
    """
    np.random.seed(random_seed)

    # 1. Patient demographics
    age = np.random.randint(18, 86, size=n_samples)

    # 2. Number of active medications (1 to 9)
    base_meds = np.random.choice([1, 2, 3, 4, 5, 6, 7, 8], size=n_samples, p=[0.25, 0.30, 0.20, 0.12, 0.06, 0.04, 0.02, 0.01])
    num_medications = base_meds

    # 3. Treatment duration in days (7 to 365)
    duration_short = np.random.randint(7, 30, size=n_samples)
    duration_med = np.random.randint(31, 90, size=n_samples)
    duration_long = np.random.randint(91, 365, size=n_samples)
    duration_choice = np.random.choice([0, 1, 2], size=n_samples, p=[0.30, 0.35, 0.35])
    treatment_duration = np.where(
        duration_choice == 0, duration_short, np.where(duration_choice == 1, duration_med, duration_long)
    )

    # 4. Patient adherence archetype to ensure balanced representation:
    # 0: Highly adherent (~45%), 1: Moderately adherent (~35%), 2: Poor adherence (~20%)
    archetype = np.random.choice([0, 1, 2], size=n_samples, p=[0.45, 0.35, 0.20])

    past_missed_appointments = np.zeros(n_samples, dtype=int)
    past_missed_doses = np.zeros(n_samples, dtype=int)

    for i in range(n_samples):
        arch = archetype[i]
        if arch == 0:  # Highly Adherent
            past_missed_appointments[i] = np.random.choice([0, 1], p=[0.92, 0.08])
            past_missed_doses[i] = np.random.choice([0, 1], p=[0.82, 0.18])
        elif arch == 1:  # Moderate / Emerging Risk
            past_missed_appointments[i] = np.random.choice([0, 1, 2], p=[0.40, 0.45, 0.15])
            past_missed_doses[i] = np.random.choice([1, 2, 3, 4], p=[0.25, 0.40, 0.25, 0.10])
        else:  # High Non-Adherence
            past_missed_appointments[i] = np.random.choice([1, 2, 3, 4, 5], p=[0.10, 0.35, 0.30, 0.15, 0.10])
            past_missed_doses[i] = np.random.randint(4, 15)

    # Class labels based on clinical criteria
    risk_levels = []
    for i in range(n_samples):
        doses = past_missed_doses[i]
        appts = past_missed_appointments[i]
        meds = num_medications[i]
        dur = treatment_duration[i]

        # Clinical decision boundary logic
        if doses >= 4 or appts >= 3 or (doses >= 3 and appts >= 2) or (doses >= 3 and meds >= 5):
            risk_levels.append("High")
        elif doses >= 2 or appts >= 1 or (doses == 1 and meds >= 4 and dur > 90):
            risk_levels.append("Medium")
        else:
            risk_levels.append("Low")

    df = pd.DataFrame(
        {
            "age": age,
            "past_missed_doses": past_missed_doses,
            "past_missed_appointments": past_missed_appointments,
            "treatment_duration_days": treatment_duration,
            "num_medications": num_medications,
            "risk_level": risk_levels,
        }
    )
    return df


def train_and_export_model(save_path: str = MODEL_OUTPUT_PATH):
    """
    Trains RandomForestClassifier, evaluates performance, and serializes model bundle.
    """
    print("Generating synthetic patient adherence training dataset...")
    df = generate_synthetic_data(n_samples=5000)

    X = df[FEATURE_NAMES]
    y = df["risk_level"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"Training set size: {len(X_train)} | Test set size: {len(X_test)}")
    print("Class distribution in training set:")
    print(y_train.value_counts(normalize=True).round(3))

    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=12,
        min_samples_split=4,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\nModel Accuracy: {accuracy:.4f}")
    print("\nClassification Report:\n", classification_report(y_test, y_pred))

    feature_importances = dict(
        zip(FEATURE_NAMES, [round(float(v), 4) for v in clf.feature_importances_])
    )
    print("Feature Importances:", feature_importances)

    model_bundle = {
        "model": clf,
        "feature_names": FEATURE_NAMES,
        "classes": list(clf.classes_),
        "accuracy": float(accuracy),
        "feature_importances": feature_importances,
    }

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(model_bundle, save_path)
    print(f"Model successfully exported to: {save_path}")
    return model_bundle


if __name__ == "__main__":
    train_and_export_model()
