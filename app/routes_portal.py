"""
Web portal routing module for HealthGuard.
Serves interactive HTML interfaces for Patients, Doctors, Administrators, and ML Simulator.
"""

import json
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import query_db, execute_db
from ml.predictor import predict_adherence_risk

portal_bp = Blueprint("portal", __name__)


@portal_bp.route("/")
def index():
    """Platform landing page with portal directory and quick-access selector."""
    doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY id ASC;")
    patients = query_db("SELECT id, name, age FROM patients ORDER BY id ASC;")
    kpis = {
        "patients": len(patients),
        "doctors": len(doctors),
        "active_rx": query_db("SELECT COUNT(*) as c FROM prescriptions WHERE status = 'Active';", one=True)["c"],
    }
    return render_template("index.html", doctors=doctors, patients=patients, kpis=kpis)


@portal_bp.route("/patient/<int:patient_id>")
def patient_portal(patient_id: int):
    """Patient Portal: view prescriptions, mark medication intake, and view follow-ups."""
    patient = query_db(
        """SELECT p.*, d.name as doctor_name, d.specialty as doctor_specialty, d.email as doctor_email, d.phone as doctor_phone
           FROM patients p
           LEFT JOIN doctors d ON p.doctor_id = d.id
           WHERE p.id = ?;""",
        (patient_id,),
        one=True,
    )
    if not patient:
        return render_template("404.html", message=f"Patient #{patient_id} not found"), 404

    # All patients for quick switcher in top nav
    all_patients = query_db("SELECT id, name FROM patients ORDER BY id ASC;")

    # Prescriptions
    prescriptions = query_db(
        """SELECT * FROM prescriptions 
           WHERE patient_id = ? 
           ORDER BY CASE status WHEN 'Active' THEN 1 ELSE 2 END, id DESC;""",
        (patient_id,),
    )

    # Today's dose check: which active prescriptions have already been logged today?
    today_str = date.today().isoformat()
    today_logs = query_db(
        """SELECT prescription_id, status, logged_time 
           FROM adherence_logs 
           WHERE patient_id = ? AND DATE(scheduled_time) = ?;""",
        (patient_id, today_str),
    )
    logged_rx_today = {row["prescription_id"]: row["status"] for row in today_logs}

    # Adherence statistics
    stats = query_db(
        """SELECT 
               COUNT(*) as total,
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed,
               SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late
           FROM adherence_logs WHERE patient_id = ?;""",
        (patient_id,),
        one=True,
    )
    total_logs = stats["total"] or 0
    taken_logs = stats["taken"] or 0
    adherence_rate = round((taken_logs / total_logs) * 100, 1) if total_logs > 0 else 100.0

    # Follow-ups
    upcoming_followups = query_db(
        """SELECT * FROM follow_up_schedules 
           WHERE patient_id = ? 
           ORDER BY appointment_date ASC;""",
        (patient_id,),
    )

    # Latest Risk Assessment
    risk_assessment = query_db(
        """SELECT * FROM risk_assessments WHERE patient_id = ? ORDER BY evaluated_at DESC, id DESC LIMIT 1;""",
        (patient_id,),
        one=True,
    )

    return render_template(
        "patient.html",
        patient=patient,
        all_patients=all_patients,
        prescriptions=prescriptions,
        logged_rx_today=logged_rx_today,
        adherence_rate=adherence_rate,
        stats=stats,
        upcoming_followups=upcoming_followups,
        risk_assessment=risk_assessment,
        today_date=today_str,
    )


@portal_bp.route("/doctor/<int:doctor_id>")
def doctor_portal(doctor_id: int):
    """Doctor Portal: patient roster, ML adherence risk indicators, and prescription manager."""
    doctor = query_db("SELECT * FROM doctors WHERE id = ?;", (doctor_id,), one=True)
    if not doctor:
        return render_template("404.html", message=f"Doctor #{doctor_id} not found"), 404

    all_doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY id ASC;")

    risk_filter = request.args.get("risk", "All")

    query = """
        SELECT 
            p.id, p.name, p.age, p.gender, p.phone, p.email, p.chronic_conditions,
            r.risk_level, r.risk_score, r.recommendations, r.evaluated_at,
            (SELECT COUNT(*) FROM prescriptions rx WHERE rx.patient_id = p.id AND rx.status = 'Active') as active_meds_count,
            (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id AND al.status = 'Missed') as total_missed_doses,
            (SELECT COUNT(*) FROM follow_up_schedules fs WHERE fs.patient_id = p.id AND fs.status = 'Missed') as total_missed_appts
        FROM patients p
        LEFT JOIN risk_assessments r ON r.id = (
            SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC, id DESC LIMIT 1
        )
        WHERE p.doctor_id = ?
    """
    params = [doctor_id]

    if risk_filter in ["Low", "Medium", "High"]:
        query += " AND r.risk_level = ?"
        params.append(risk_filter)

    query += " ORDER BY CASE r.risk_level WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, p.name ASC;"

    assigned_patients = query_db(query, tuple(params))

    # Doctor statistics
    counts = query_db(
        """SELECT 
               COUNT(p.id) as total_patients,
               SUM(CASE WHEN r.risk_level = 'High' THEN 1 ELSE 0 END) as high_risk,
               SUM(CASE WHEN r.risk_level = 'Medium' THEN 1 ELSE 0 END) as med_risk,
               SUM(CASE WHEN r.risk_level = 'Low' THEN 1 ELSE 0 END) as low_risk
           FROM patients p
           LEFT JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC, id DESC LIMIT 1
           )
           WHERE p.doctor_id = ?;""",
        (doctor_id,),
        one=True,
    )

    return render_template(
        "doctor.html",
        doctor=doctor,
        all_doctors=all_doctors,
        patients=assigned_patients,
        stats=counts,
        current_filter=risk_filter,
    )


@portal_bp.route("/admin")
def admin_dashboard():
    """Admin Dashboard: aggregate population statistics, adherence trends, and high-risk cohort."""
    total_patients = query_db("SELECT COUNT(*) as count FROM patients;", one=True)["count"]
    total_doctors = query_db("SELECT COUNT(*) as count FROM doctors;", one=True)["count"]
    total_active_rx = query_db("SELECT COUNT(*) as count FROM prescriptions WHERE status = 'Active';", one=True)["count"]

    # Adherence metrics
    stats = query_db(
        """SELECT 
               COUNT(*) as total,
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed,
               SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late
           FROM adherence_logs;""",
        one=True,
    )
    total_logs = stats["total"] or 0
    taken_logs = stats["taken"] or 0
    adherence_rate = round((taken_logs / total_logs) * 100, 1) if total_logs > 0 else 100.0

    # Risk level breakdown
    risk_summary = query_db(
        """SELECT r.risk_level, COUNT(*) as count
           FROM risk_assessments r
           INNER JOIN (
               SELECT patient_id, MAX(id) as max_id
               FROM risk_assessments
               GROUP BY patient_id
           ) latest ON r.id = latest.max_id
           GROUP BY r.risk_level;"""
    )
    risk_map = {"Low": 0, "Medium": 0, "High": 0}
    for row in risk_summary:
        risk_map[row["risk_level"]] = row["count"]

    # High Risk Patients list with doctor contact
    high_risk_roster = query_db(
        """SELECT 
               p.id, p.name, p.age, p.gender, p.phone, p.chronic_conditions,
               d.name as doctor_name, d.specialty as doctor_specialty,
               r.risk_score, r.recommendations, r.evaluated_at,
               (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id AND al.status = 'Missed') as missed_doses
           FROM patients p
           JOIN doctors d ON p.doctor_id = d.id
           JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC, id DESC LIMIT 1
           )
           WHERE r.risk_level = 'High'
           ORDER BY r.risk_score DESC;"""
    )

    # 7-day adherence trends for charts
    trends = query_db(
        """SELECT 
               DATE(logged_time) as log_date,
               SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
               SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed
           FROM adherence_logs
           WHERE logged_time >= DATE('now', '-7 days')
           GROUP BY DATE(logged_time)
           ORDER BY log_date ASC;"""
    )
    chart_dates = [t["log_date"] for t in trends]
    chart_taken = [t["taken"] for t in trends]
    chart_missed = [t["missed"] for t in trends]

    return render_template(
        "admin.html",
        total_patients=total_patients,
        total_doctors=total_doctors,
        total_active_rx=total_active_rx,
        adherence_rate=adherence_rate,
        total_logs=total_logs,
        missed_logs=stats["missed"] or 0,
        risk_map=risk_map,
        high_risk_patients=high_risk_roster,
        chart_dates_json=json.dumps(chart_dates),
        chart_taken_json=json.dumps(chart_taken),
        chart_missed_json=json.dumps(chart_missed),
        risk_distribution_json=json.dumps([risk_map["Low"], risk_map["Medium"], risk_map["High"]]),
    )


@portal_bp.route("/simulator", methods=["GET", "POST"])
def simulator():
    """ML Risk Predictor interactive sandbox for clinicians and testers."""
    prediction_result = None
    form_data = {
        "age": 65,
        "past_missed_doses": 3,
        "past_missed_appointments": 1,
        "treatment_duration_days": 90,
        "num_medications": 4,
    }

    if request.method == "POST":
        try:
            form_data = {
                "age": int(request.form.get("age", 65)),
                "past_missed_doses": int(request.form.get("past_missed_doses", 0)),
                "past_missed_appointments": int(request.form.get("past_missed_appointments", 0)),
                "treatment_duration_days": int(request.form.get("treatment_duration_days", 30)),
                "num_medications": int(request.form.get("num_medications", 1)),
            }
            prediction_result = predict_adherence_risk(**form_data)
        except Exception as e:
            flash(f"Error calculating risk prediction: {str(e)}", "danger")

    return render_template(
        "simulator.html",
        form_data=form_data,
        result=prediction_result,
    )
