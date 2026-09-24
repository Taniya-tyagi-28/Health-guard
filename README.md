# HealthGuard: Predictive Patient Follow-Up & Medication Adherence Platform

**HealthGuard** is an intelligent healthcare platform designed to proactively detect and mitigate patient medication non-adherence and missed appointments. Combining a **Scikit-Learn Random Forest** classification model with an **SQLite** database, **Flask REST APIs**, and responsive **Clinical Portals**, the platform provides role-tailored workflows for patients, physicians, and healthcare administrators.

---

## Architecture Overview

```
p/
├── database/
│   ├── __init__.py
│   ├── schema.sql              # Relational schema (DDL) with foreign keys & check constraints
│   ├── db.py                   # SQLite connection helpers & transactional queries
│   └── seed_data.py            # Clinical dataset generator (doctors, patients, prescriptions, logs)
├── ml/
│   ├── __init__.py
│   ├── train_model.py          # Synthetic clinical dataset generator, RF model trainer & evaluator
│   ├── predictor.py            # Feature validation, ML inference engine & intervention recommendations
│   └── healthguard_model.joblib # Serialized model bundle & metadata
├── app/
│   ├── __init__.py             # Flask application factory
│   ├── routes_portal.py        # Web portal routes (Patient, Doctor, Admin, Simulator)
│   ├── routes_api.py           # REST APIs (/api/predict, /api/patients, /api/prescriptions, etc.)
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css       # Modern clinical design system, dark-mode glassmorphism, responsive
│   │   └── js/
│   │       └── main.js         # Real-time dose logging, prescription modal, Chart.js integrations
│   └── templates/
│       ├── base.html           # Unified navigation, alerts, and tech footer
│       ├── index.html          # Overview & role portal switcher
│       ├── patient.html        # Patient Portal: daily schedule, 1-click dose logger, follow-ups
│       ├── doctor.html         # Doctor Portal: patient roster, ML risk alert badges, Add Rx modal
│       ├── admin.html          # Admin Dashboard: population KPIs, Chart.js trends, high-risk queue
│       ├── simulator.html      # Interactive ML risk sandbox for clinicians
│       └── 404.html            # Error page
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures (isolated temporary DB & Flask test client)
│   ├── test_models_and_validation.py # Unit tests: feature bounds, classification, recommendations
│   ├── test_api.py             # API tests: Predict, Patients, Prescriptions, Adherence, Analytics
│   └── test_database_integrity.py    # DB tests: foreign keys, constraints, cascade delete, log persistence
├── app.py                      # Flask main entry point
├── streamlit_app.py            # Interactive Streamlit companion application
├── requirements.txt            # Dependency specifications
└── README.md                   # Documentation & setup guide
```

---

## Core Modules

### 1. Database & Schemas (`database/`)
- **`doctors`**: Physician profiles, specialties, and contact info.
- **`patients`**: Demographics (Age 0-125), chronic conditions, assigned doctor.
- **`prescriptions`**: Medication name, dosage, frequency, treatment duration (days), status (`Active`, `Completed`, `Discontinued`).
- **`adherence_logs`**: Scheduled intake time, actual log timestamp, status (`Taken`, `Missed`, `Late`), notes.
- **`follow_up_schedules`**: Clinical appointment schedules and status (`Scheduled`, `Attended`, `Missed`, `Cancelled`).
- **`risk_assessments`**: Inferred risk levels (`Low`, `Medium`, `High`), confidence percentages, feature snapshot JSON, and intervention guidance.

### 2. Machine Learning Engine (`ml/`)
- **Algorithm**: `RandomForestClassifier` (120 estimators, class balanced, depth 12).
- **Features**:
  1. `age` (18 - 95 years)
  2. `past_missed_doses` (0 - 25 doses)
  3. `past_missed_appointments` (0 - 6 missed clinical visits)
  4. `treatment_duration_days` (7 - 365 days)
  5. `num_medications` (Polypharmacy count: 1 - 10 active medications)
- **Target Output**: Stratified Risk Level:
  - **`Low`**: Adherence $\ge 85\%$, 0-1 missed doses $\rightarrow$ standard clinical follow-up.
  - **`Medium`**: Emerging risk $\rightarrow$ automated SMS check-ins and refill alerts.
  - **`High`**: Critical non-adherence $\rightarrow$ immediate care coordination outreach & regimen review.

### 3. Application Portals
- **Patient Portal (`/patient/<id>`)**: View active prescriptions, mark today's dose as "Taken" or "Missed" with 1-click instant updates, inspect real-time adherence percentage, and check upcoming appointment dates.
- **Doctor Portal (`/doctor/<id>`)**: Inspect assigned patient roster, view real-time ML risk badges, filter by risk level, and prescribe new medications via modal dialog.
- **Admin Dashboard (`/admin`)**: Population-wide adherence metrics, Chart.js weekly adherence trend line chart, risk distribution donut chart, and high-risk patient intervention queue.
- **ML Simulator (`/simulator`)**: Interactive sandbox for researchers to simulate what-if scenarios across all 5 features.

### 4. RESTful API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/predict` | Evaluates ML adherence risk for given patient features. |
| `GET` | `/api/patients` | Retrieves all patients with real-time risk scores and adherence rates. |
| `GET` | `/api/patients/<id>` | Comprehensive patient profile with prescriptions and adherence history. |
| `POST` | `/api/prescriptions` | Creates a new prescription and triggers risk recalculation. |
| `PUT` | `/api/prescriptions/<id>` | Updates prescription status (`Active`, `Completed`, `Discontinued`). |
| `POST` | `/api/adherence` | Logs medication intake (`Taken`, `Missed`, `Late`) and updates patient risk. |
| `GET` | `/api/analytics` | Returns aggregate population metrics and trend series. |

---

## Getting Started

### 1. Installation
Ensure Python 3.10+ is installed:
```powershell
pip install -r requirements.txt
```

### 2. Train the ML Model
Train the Random Forest model and generate `ml/healthguard_model.joblib`:
```powershell
python ml/train_model.py
```

### 3. Initialize & Seed Database
Seed the SQLite database (`healthguard.db`) with sample doctors, patients, prescriptions, and adherence history:
```powershell
python database/seed_data.py
```

### 4. Run the Web Application
Start the Flask application:
```powershell
python app.py
```
Open your browser at:
- **Platform Overview**: [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Patient Portal**: [http://127.0.0.1:5000/patient/1](http://127.0.0.1:5000/patient/1)
- **Doctor Portal**: [http://127.0.0.1:5000/doctor/1](http://127.0.0.1:5000/doctor/1)
- **Admin Dashboard**: [http://127.0.0.1:5000/admin](http://127.0.0.1:5000/admin)
- **ML Simulator**: [http://127.0.0.1:5000/simulator](http://127.0.0.1:5000/simulator)

### 5. (Optional) Run the Streamlit Companion App
To explore the Streamlit interface:
```powershell
streamlit run streamlit_app.py
```

---

## Running the Automated Test Suite

HealthGuard includes a dedicated `tests/` directory with 36 comprehensive tests covering:
- **Unit & Functional Tests**: ML input validation, feature boundaries, and classification output.
- **REST API Tests**: Predict, Patients, Prescriptions, Adherence, and Analytics endpoints.
- **Database Integrity Tests**: Foreign key constraints, check constraints, cascade deletions, and log persistence.

Run the test suite with:
```powershell
pytest -v
```
All 36 tests execute against isolated temporary SQLite databases and pass cleanly.
