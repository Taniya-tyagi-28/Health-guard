"""
RESTful API routes for HealthGuard platform.
Handles prediction inference, patient management, prescription updates,
dose adherence logging, and population health analytics.
"""

import json
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from database.db import query_db, execute_db
from ml.predictor import predict_adherence_risk, validate_prediction_inputs

api_bp = Blueprint("api", __name__, url_prefix="/api")


def update_patient_risk_assessment(patient_id: int):
    """
    Recalculates patient features from database, triggers ML prediction,
    and saves the new assessment.
    """
    patient = query_db("SELECT id, age FROM patients WHERE id = ?;", (patient_id,), one=True)
    if not patient:
        return None

    # Count missed doses
    missed_doses_row = query_db(
        "SELECT COUNT(*) as count FROM adherence_logs WHERE patient_id = ? AND status = 'Missed';",
        (patient_id,),
        one=True,
    )
    missed_doses = missed_doses_row["count"] if missed_doses_row else 0

    # Count missed appointments
    missed_appts_row = query_db(
        "SELECT COUNT(*) as count FROM follow_up_schedules WHERE patient_id = ? AND status = 'Missed';",
        (patient_id,),
        one=True,
    )
    missed_appts = missed_appts_row["count"] if missed_appts_row else 0

    # Prescription stats
    rx_stats = query_db(
        """SELECT COUNT(*) as num_meds, AVG(treatment_duration_days) as avg_duration
           FROM prescriptions WHERE patient_id = ? AND status = 'Active';""",
        (patient_id,),
        one=True,
    )
    num_meds = max(1, rx_stats["num_meds"] or 1)
    duration = int(rx_stats["avg_duration"] or 30)

    # Run ML inference
    result = predict_adherence_risk(
        age=patient["age"],
        past_missed_doses=missed_doses,
        past_missed_appointments=missed_appts,
        treatment_duration_days=duration,
        num_medications=num_meds,
    )

    execute_db(
        """INSERT INTO risk_assessments (patient_id, risk_level, risk_score, features_json, recommendations)
           VALUES (?, ?, ?, ?, ?);""",
        (
            patient_id,
            result["risk_level"],
            result["confidence"],
            json.dumps(result["features"]),
            result["recommendations"],
        ),
    )
    return result


@api_bp.route("/predict", methods=["POST"])
def api_predict():
    """
    POST /api/predict
    Evaluates medication adherence risk based on patient features.
    Payload: {
        "age": int,
        "past_missed_doses": int,
        "past_missed_appointments": int,
        "treatment_duration_days": int,
        "num_medications": int,
        "patient_id": optional int
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request. JSON body is required."}), 400

    required_keys = [
        "age",
        "past_missed_doses",
        "past_missed_appointments",
        "treatment_duration_days",
        "num_medications",
    ]
    missing = [k for k in required_keys if k not in data]
    if missing:
        return (
            jsonify({"error": f"Missing required feature keys: {', '.join(missing)}"}),
            400,
        )

    try:
        prediction = predict_adherence_risk(
            age=data["age"],
            past_missed_doses=data["past_missed_doses"],
            past_missed_appointments=data["past_missed_appointments"],
            treatment_duration_days=data["treatment_duration_days"],
            num_medications=data["num_medications"],
        )

        # If a patient_id is linked, record this prediction in the database
        patient_id = data.get("patient_id")
        if patient_id:
            patient = query_db("SELECT id FROM patients WHERE id = ?;", (patient_id,), one=True)
            if patient:
                execute_db(
                    """INSERT INTO risk_assessments (patient_id, risk_level, risk_score, features_json, recommendations)
                       VALUES (?, ?, ?, ?, ?);""",
                    (
                        patient_id,
                        prediction["risk_level"],
                        prediction["confidence"],
                        json.dumps(prediction["features"]),
                        prediction["recommendations"],
                    ),
                )

        return jsonify({"status": "success", "prediction": prediction}), 200

    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 422
    except Exception as exc:
        return jsonify({"error": f"Internal server error during prediction: {str(exc)}"}), 500


@api_bp.route("/patients", methods=["GET"])
def get_patients():
    """
    GET /api/patients
    Returns list of patients with latest risk score, adherence stats, and doctor info.
    Optional query filters: ?doctor_id=<id>&risk_level=<Low|Medium|High>
    """
    doctor_id = request.args.get("doctor_id")
    risk_level = request.args.get("risk_level")

    query = """
        SELECT 
            p.id, p.name, p.age, p.gender, p.phone, p.email, p.chronic_conditions,
            d.id as doctor_id, d.name as doctor_name, d.specialty as doctor_specialty,
            r.risk_level, r.risk_score, r.recommendations, r.evaluated_at,
            (SELECT COUNT(*) FROM prescriptions rx WHERE rx.patient_id = p.id AND rx.status = 'Active') as active_prescriptions_count,
            (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id AND al.status = 'Taken') as doses_taken,
            (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id AND al.status = 'Missed') as doses_missed,
            (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id) as total_doses_logged
        FROM patients p
        LEFT JOIN doctors d ON p.doctor_id = d.id
        LEFT JOIN risk_assessments r ON r.id = (
            SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC, id DESC LIMIT 1
        )
        WHERE 1=1
    """
    params = []
    if doctor_id:
        query += " AND p.doctor_id = ?"
        params.append(doctor_id)
    if risk_level:
        query += " AND r.risk_level = ?"
        params.append(risk_level)

    query += " ORDER BY CASE r.risk_level WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, p.name ASC;"

    patients = query_db(query, tuple(params))
    # Calculate adherence rate percentage
    for pt in patients:
        total = pt["total_doses_logged"] or 0
        taken = pt["doses_taken"] or 0
        pt["adherence_rate"] = round((taken / total * 100), 1) if total > 0 else 100.0

    return jsonify({"patients": patients, "count": len(patients)}), 200


@api_bp.route("/patients/<int:patient_id>", methods=["GET"])
def get_patient_detail(patient_id: int):
    """
    GET /api/patients/<id>
    Returns comprehensive profile: patient info, active prescriptions,
    adherence logs, upcoming follow-ups, and latest risk assessment.
    """
    patient = query_db(
        """SELECT p.*, d.name as doctor_name, d.specialty as doctor_specialty, d.email as doctor_email
           FROM patients p
           LEFT JOIN doctors d ON p.doctor_id = d.id
           WHERE p.id = ?;""",
        (patient_id,),
        one=True,
    )
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    # Prescriptions
    prescriptions = query_db(
        """SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY status ASC, created_at DESC;""",
        (patient_id,),
    )

    # Recent Adherence logs (last 20)
    logs = query_db(
        """SELECT al.*, pr.medication_name, pr.dosage
           FROM adherence_logs al
           JOIN prescriptions pr ON al.prescription_id = pr.id
           WHERE al.patient_id = ?
           ORDER BY al.logged_time DESC, al.id DESC LIMIT 20;""",
        (patient_id,),
    )

    # Follow-up schedules
    follow_ups = query_db(
        """SELECT * FROM follow_up_schedules WHERE patient_id = ? ORDER BY appointment_date ASC;""",
        (patient_id,),
    )

    # Latest risk assessment
    latest_risk = query_db(
        """SELECT * FROM risk_assessments WHERE patient_id = ? ORDER BY evaluated_at DESC, id DESC LIMIT 1;""",
        (patient_id,),
        one=True,
    )
    if latest_risk and latest_risk["features_json"]:
        try:
            latest_risk["features"] = json.loads(latest_risk["features_json"])
        except Exception:
            latest_risk["features"] = {}

    # Calculate Adherence Rate
    counts = query_db(
        """SELECT 
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed,
               SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late,
               COUNT(*) as total
           FROM adherence_logs WHERE patient_id = ?;""",
        (patient_id,),
        one=True,
    )
    total_logs = counts["total"] or 0
    taken_logs = counts["taken"] or 0
    adherence_rate = round((taken_logs / total_logs) * 100, 1) if total_logs > 0 else 100.0

    return (
        jsonify(
            {
                "patient": patient,
                "prescriptions": prescriptions,
                "recent_adherence_logs": logs,
                "follow_up_schedules": follow_ups,
                "latest_risk_assessment": latest_risk,
                "adherence_statistics": {
                    "rate_percentage": adherence_rate,
                    "taken": taken_logs,
                    "missed": counts["missed"] or 0,
                    "late": counts["late"] or 0,
                    "total": total_logs,
                },
            }
        ),
        200,
    )


@api_bp.route("/patients", methods=["POST"])
def create_patient():
    """
    POST /api/patients
    Registers a new patient and runs baseline ML adherence risk evaluation.
    Payload: {
        "name": str,
        "age": int (0-125),
        "gender": optional ("Male" | "Female" | "Other"),
        "phone": optional str,
        "email": optional str,
        "chronic_conditions": optional str,
        "doctor_id": optional int,
        "past_missed_doses": optional int (default 0),
        "past_missed_appointments": optional int (default 0)
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body is required"}), 400

    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    if not name:
        return jsonify({"error": "Patient name is required"}), 400

    if "age" not in data or data["age"] is None:
        return jsonify({"error": "Patient age is required"}), 400

    try:
        age = int(data["age"])
        if age < 0 or age > 125:
            return jsonify({"error": "Age must be between 0 and 125"}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "Age must be a valid integer"}), 400

    gender = data.get("gender", "Other")
    if gender not in ["Male", "Female", "Other"]:
        gender = "Other"

    phone = data.get("phone", "").strip() if isinstance(data.get("phone"), str) else None
    email = data.get("email", "").strip() if isinstance(data.get("email"), str) else None
    if email == "":
        email = None

    if email:
        existing = query_db("SELECT id FROM patients WHERE email = ?;", (email,), one=True)
        if existing:
            return jsonify({"error": f"A patient with email '{email}' already exists"}), 409

    doctor_id = data.get("doctor_id")
    if doctor_id:
        doc = query_db("SELECT id FROM doctors WHERE id = ?;", (doctor_id,), one=True)
        if not doc:
            return jsonify({"error": f"Doctor with ID {doctor_id} not found"}), 404
    else:
        doc = query_db("SELECT id FROM doctors ORDER BY id ASC LIMIT 1;", one=True)
        doctor_id = doc["id"] if doc else None

    chronic_conditions = data.get("chronic_conditions", "").strip()

    patient_id = execute_db(
        """INSERT INTO patients (doctor_id, name, age, gender, phone, email, chronic_conditions)
           VALUES (?, ?, ?, ?, ?, ?, ?);""",
        (doctor_id, name, age, gender, phone, email, chronic_conditions),
    )

    # Initial baseline ML risk assessment
    past_missed_doses = int(data.get("past_missed_doses", 0))
    past_missed_appts = int(data.get("past_missed_appointments", 0))
    try:
        prediction = predict_adherence_risk(
            age=age,
            past_missed_doses=past_missed_doses,
            past_missed_appointments=past_missed_appts,
            treatment_duration_days=30,
            num_medications=1,
        )
        execute_db(
            """INSERT INTO risk_assessments (patient_id, risk_level, risk_score, features_json, recommendations)
               VALUES (?, ?, ?, ?, ?);""",
            (
                patient_id,
                prediction["risk_level"],
                prediction["confidence"],
                json.dumps(prediction["features"]),
                prediction["recommendations"],
            ),
        )
    except Exception:
        prediction = None

    return (
        jsonify(
            {
                "status": "success",
                "message": f"Patient '{name}' created successfully",
                "patient_id": patient_id,
                "baseline_risk": prediction,
            }
        ),
        201,
    )


@api_bp.route("/doctors", methods=["GET"])
def get_doctors():
    """GET /api/doctors: Returns list of all doctors."""
    doctors = query_db("SELECT * FROM doctors ORDER BY name ASC;")
    return jsonify({"doctors": doctors, "count": len(doctors)}), 200


@api_bp.route("/doctors", methods=["POST"])
def create_doctor():
    """
    POST /api/doctors
    Registers a new physician profile.
    Payload: {
        "name": str,
        "specialty": str,
        "email": str,
        "phone": optional str
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body is required"}), 400

    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    specialty = data.get("specialty", "").strip() if isinstance(data.get("specialty"), str) else ""
    email = data.get("email", "").strip() if isinstance(data.get("email"), str) else ""
    phone = data.get("phone", "").strip() if isinstance(data.get("phone"), str) else None

    if not name:
        return jsonify({"error": "Doctor name is required"}), 400
    if not specialty:
        return jsonify({"error": "Specialty is required"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400

    existing = query_db("SELECT id FROM doctors WHERE email = ?;", (email,), one=True)
    if existing:
        return jsonify({"error": f"Doctor with email '{email}' already exists"}), 409

    doc_id = execute_db(
        "INSERT INTO doctors (name, specialty, email, phone) VALUES (?, ?, ?, ?);",
        (name, specialty, email, phone),
    )

    return (
        jsonify(
            {
                "status": "success",
                "message": f"Doctor '{name}' registered successfully",
                "doctor_id": doc_id,
            }
        ),
        201,
    )


@api_bp.route("/follow-ups", methods=["POST"])
def create_follow_up():
    """
    POST /api/follow-ups
    Schedules a new clinical follow-up appointment.
    Payload: {
        "patient_id": int,
        "doctor_id": int,
        "appointment_date": str,
        "notes": optional str,
        "status": optional str
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body is required"}), 400

    patient_id = data.get("patient_id")
    doctor_id = data.get("doctor_id")
    appt_date = data.get("appointment_date")
    notes = data.get("notes", "").strip() if isinstance(data.get("notes"), str) else ""
    status = data.get("status", "Scheduled")

    if not patient_id or not doctor_id or not appt_date:
        return jsonify({"error": "patient_id, doctor_id, and appointment_date are required"}), 400

    p = query_db("SELECT id FROM patients WHERE id = ?;", (patient_id,), one=True)
    if not p:
        return jsonify({"error": f"Patient #{patient_id} not found"}), 404

    d = query_db("SELECT id FROM doctors WHERE id = ?;", (doctor_id,), one=True)
    if not d:
        return jsonify({"error": f"Doctor #{doctor_id} not found"}), 404

    fu_id = execute_db(
        """INSERT INTO follow_up_schedules (patient_id, doctor_id, appointment_date, status, notes)
           VALUES (?, ?, ?, ?, ?);""",
        (patient_id, doctor_id, appt_date, status, notes),
    )

    return (
        jsonify(
            {
                "status": "success",
                "message": "Follow-up appointment scheduled successfully",
                "schedule_id": fu_id,
            }
        ),
        201,
    )


@api_bp.route("/prescriptions", methods=["POST"])
def create_prescription():
    """
    POST /api/prescriptions
    Creates a new prescription for a patient and prompts risk update.
    Payload: {
        "patient_id": int,
        "doctor_id": int,
        "medication_name": str,
        "dosage": str,
        "frequency": str,
        "instructions": optional str,
        "start_date": optional YYYY-MM-DD,
        "treatment_duration_days": int
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body is required"}), 400

    required = ["patient_id", "doctor_id", "medication_name", "dosage", "frequency", "treatment_duration_days"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # Verify patient & doctor exist
    patient = query_db("SELECT id FROM patients WHERE id = ?;", (data["patient_id"],), one=True)
    if not patient:
        return jsonify({"error": f"Patient with ID {data['patient_id']} does not exist"}), 404

    doctor = query_db("SELECT id FROM doctors WHERE id = ?;", (data["doctor_id"],), one=True)
    if not doctor:
        return jsonify({"error": f"Doctor with ID {data['doctor_id']} does not exist"}), 404

    try:
        duration = int(data["treatment_duration_days"])
        if duration <= 0:
            return jsonify({"error": "treatment_duration_days must be a positive integer"}), 400
    except ValueError:
        return jsonify({"error": "treatment_duration_days must be an integer"}), 400

    start_date = data.get("start_date") or date.today().isoformat()
    try:
        from datetime import datetime as dt, timedelta as td
        start_dt = dt.strptime(start_date, "%Y-%m-%d")
        end_date = (start_dt + td(days=duration)).strftime("%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid start_date format, expected YYYY-MM-DD"}), 400

    rx_id = execute_db(
        """INSERT INTO prescriptions 
           (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, end_date, treatment_duration_days, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active');""",
        (
            data["patient_id"],
            data["doctor_id"],
            data["medication_name"].strip(),
            data["dosage"].strip(),
            data["frequency"].strip(),
            data.get("instructions", "").strip(),
            start_date,
            end_date,
            duration,
        ),
    )

    # Re-evaluate patient's risk profile with the new prescription
    updated_risk = update_patient_risk_assessment(data["patient_id"])

    return (
        jsonify(
            {
                "status": "success",
                "message": "Prescription created successfully",
                "prescription_id": rx_id,
                "updated_risk": updated_risk,
            }
        ),
        201,
    )


@api_bp.route("/prescriptions/<int:prescription_id>", methods=["PUT"])
def update_prescription_status(prescription_id: int):
    """
    PUT /api/prescriptions/<id>
    Updates status: 'Active', 'Completed', or 'Discontinued'.
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ["Active", "Completed", "Discontinued"]:
        return jsonify({"error": "Invalid status. Must be 'Active', 'Completed', or 'Discontinued'"}), 400

    rx = query_db("SELECT id, patient_id FROM prescriptions WHERE id = ?;", (prescription_id,), one=True)
    if not rx:
        return jsonify({"error": "Prescription not found"}), 404

    execute_db("UPDATE prescriptions SET status = ? WHERE id = ?;", (new_status, prescription_id))
    updated_risk = update_patient_risk_assessment(rx["patient_id"])

    return jsonify({"status": "success", "message": f"Prescription status updated to {new_status}", "updated_risk": updated_risk}), 200


@api_bp.route("/adherence", methods=["POST"])
def log_adherence():
    """
    POST /api/adherence
    Logs a medication dose intake ('Taken', 'Missed', 'Late')
    Payload: {
        "prescription_id": int,
        "patient_id": int,
        "status": "Taken" | "Missed" | "Late",
        "scheduled_time": optional ISO timestamp,
        "notes": optional str
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body is required"}), 400

    rx_id = data.get("prescription_id")
    p_id = data.get("patient_id")
    status = data.get("status")

    if not rx_id or not p_id or not status:
        return jsonify({"error": "prescription_id, patient_id, and status are required"}), 400

    if status not in ["Taken", "Missed", "Late"]:
        return jsonify({"error": "status must be one of: 'Taken', 'Missed', 'Late'"}), 400

    # Validate prescription ownership
    rx = query_db("SELECT id, patient_id FROM prescriptions WHERE id = ?;", (rx_id,), one=True)
    if not rx:
        return jsonify({"error": "Prescription not found"}), 404
    if rx["patient_id"] != int(p_id):
        return jsonify({"error": "Prescription does not belong to specified patient"}), 400

    scheduled_time = data.get("scheduled_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notes = data.get("notes", "").strip()

    log_id = execute_db(
        """INSERT INTO adherence_logs (prescription_id, patient_id, scheduled_time, logged_time, status, notes)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?);""",
        (rx_id, p_id, scheduled_time, status, notes),
    )

    # Immediately trigger real-time ML risk re-assessment
    new_risk = update_patient_risk_assessment(int(p_id))

    return (
        jsonify(
            {
                "status": "success",
                "message": f"Adherence status '{status}' logged successfully.",
                "log_id": log_id,
                "latest_risk": new_risk,
            }
        ),
        201,
    )


@api_bp.route("/analytics", methods=["GET"])
def get_analytics():
    """
    GET /api/analytics
    Returns population-level metrics, adherence distribution, and trend logs for Admin Dashboard.
    """
    # 1. Total counts
    total_patients = query_db("SELECT COUNT(*) as count FROM patients;", one=True)["count"]
    total_doctors = query_db("SELECT COUNT(*) as count FROM doctors;", one=True)["count"]
    total_active_prescriptions = query_db(
        "SELECT COUNT(*) as count FROM prescriptions WHERE status = 'Active';", one=True
    )["count"]

    # 2. Population adherence stats
    adherence_stats = query_db(
        """SELECT 
               COUNT(*) as total,
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed,
               SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late
           FROM adherence_logs;""",
        one=True,
    )
    total_logs = adherence_stats["total"] or 0
    taken_logs = adherence_stats["taken"] or 0
    overall_adherence_rate = (
        round((taken_logs / total_logs) * 100, 1) if total_logs > 0 else 100.0
    )

    # 3. Risk level distribution from latest assessments
    risk_counts_query = query_db(
        """SELECT r.risk_level, COUNT(*) as count
           FROM risk_assessments r
           INNER JOIN (
               SELECT patient_id, MAX(id) as max_id
               FROM risk_assessments
               GROUP BY patient_id
           ) latest ON r.id = latest.max_id
           GROUP BY r.risk_level;"""
    )
    risk_distribution = {"Low": 0, "Medium": 0, "High": 0}
    for row in risk_counts_query:
        risk_distribution[row["risk_level"]] = row["count"]

    # 4. Weekly adherence trend (past 7 days)
    trend_rows = query_db(
        """SELECT 
               DATE(logged_time) as log_date,
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed
           FROM adherence_logs
           WHERE logged_time >= DATE('now', '-7 days')
           GROUP BY DATE(logged_time)
           ORDER BY log_date ASC;"""
    )
    dates = [row["log_date"] for row in trend_rows]
    taken_trend = [row["taken"] for row in trend_rows]
    missed_trend = [row["missed"] for row in trend_rows]

    # 5. High risk patient list
    high_risk_patients = query_db(
        """SELECT 
               p.id, p.name, p.age, p.phone, p.chronic_conditions,
               d.name as doctor_name,
               r.risk_score, r.recommendations, r.evaluated_at
           FROM patients p
           JOIN doctors d ON p.doctor_id = d.id
           JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC, id DESC LIMIT 1
           )
           WHERE r.risk_level = 'High'
           ORDER BY r.risk_score DESC, p.name ASC;"""
    )

    return (
        jsonify(
            {
                "kpis": {
                    "total_patients": total_patients,
                    "total_doctors": total_doctors,
                    "total_active_prescriptions": total_active_prescriptions,
                    "overall_adherence_rate": overall_adherence_rate,
                    "total_doses_logged": total_logs,
                    "high_risk_count": risk_distribution.get("High", 0),
                    "medium_risk_count": risk_distribution.get("Medium", 0),
                    "low_risk_count": risk_distribution.get("Low", 0),
                },
                "risk_distribution": risk_distribution,
                "adherence_trend": {
                    "dates": dates,
                    "taken": taken_trend,
                    "missed": missed_trend,
                },
                "high_risk_patients": high_risk_patients,
            }
        ),
        200,
    )
