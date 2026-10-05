"""
Web portal routing module for HealthGuard.
Serves interactive HTML interfaces for Patients, Doctors, Administrators, and ML Simulator.
"""

import json
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database.db import query_db, execute_db
from ml.predictor import predict_adherence_risk
from app.auth import authenticate_user, register_new_user, ensure_auth_tables

portal_bp = Blueprint("portal", __name__)


@portal_bp.route("/overview")
@portal_bp.route("/portal")
@portal_bp.route("/index")
def overview():
    """Platform landing page with portal directory and quick-access selector."""
    doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY id ASC;")
    patients = query_db("SELECT id, name, age FROM patients ORDER BY id ASC;")
    kpis = {
        "patients": len(patients),
        "doctors": len(doctors),
        "active_rx": query_db("SELECT COUNT(*) as c FROM prescriptions WHERE status = 'Active';", one=True)["c"],
    }
    return render_template("index.html", doctors=doctors, patients=patients, kpis=kpis)


portal_bp.add_url_rule("/overview-page", endpoint="index", view_func=overview)




@portal_bp.route("/patient")
@portal_bp.route("/patient/")
def default_patient():
    """Redirects to the default first patient portal."""
    return redirect(url_for("portal.patient_portal", patient_id=1))


@portal_bp.route("/doctor")
@portal_bp.route("/doctor/")
def default_doctor():
    """Redirects to the default first doctor portal."""
    return redirect(url_for("portal.doctor_portal", doctor_id=1))


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


@portal_bp.route("/add-data", methods=["GET", "POST"])
def add_data_portal():
    """
    Interactive Data Entry Portal:
    Allows clinical staff and administrators to add new Patients, Prescriptions,
    Follow-Up Appointments, Physicians, and Adherence Logs.
    """
    doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY name ASC;")
    patients = query_db("SELECT id, name, age FROM patients ORDER BY name ASC;")
    prescriptions = query_db(
        """SELECT pr.id, pr.medication_name, pr.dosage, pr.patient_id, p.name as patient_name
           FROM prescriptions pr
           JOIN patients p ON pr.patient_id = p.id
           WHERE pr.status = 'Active'
           ORDER BY p.name ASC;"""
    )

    active_tab = request.args.get("tab", "patient")

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "add_patient":
                name = request.form.get("name", "").strip()
                age_str = request.form.get("age", "").strip()
                if not name or not age_str:
                    flash("Patient full name and age are required.", "danger")
                    return redirect(url_for("portal.add_data_portal", tab="patient"))

                age = int(age_str)
                if age < 0 or age > 125:
                    flash("Age must be between 0 and 125.", "danger")
                    return redirect(url_for("portal.add_data_portal", tab="patient"))

                gender = request.form.get("gender", "Other")
                phone = request.form.get("phone", "").strip() or None
                email = request.form.get("email", "").strip() or None
                doctor_id = int(request.form.get("doctor_id")) if request.form.get("doctor_id") else None
                conditions = request.form.get("chronic_conditions", "").strip()

                if email:
                    existing = query_db("SELECT id FROM patients WHERE email = ?;", (email,), one=True)
                    if existing:
                        flash(f"A patient with email '{email}' already exists.", "danger")
                        return redirect(url_for("portal.add_data_portal", tab="patient"))

                new_pid = execute_db(
                    """INSERT INTO patients (doctor_id, name, age, gender, phone, email, chronic_conditions)
                       VALUES (?, ?, ?, ?, ?, ?, ?);""",
                    (doctor_id, name, age, gender, phone, email, conditions),
                )

                # Baseline ML risk assessment
                pred = predict_adherence_risk(
                    age=age,
                    past_missed_doses=0,
                    past_missed_appointments=0,
                    treatment_duration_days=30,
                    num_medications=1,
                )
                execute_db(
                    """INSERT INTO risk_assessments (patient_id, risk_level, risk_score, features_json, recommendations)
                       VALUES (?, ?, ?, ?, ?);""",
                    (new_pid, pred["risk_level"], pred["confidence"], json.dumps(pred["features"]), pred["recommendations"]),
                )
                flash(f"Patient '{name}' successfully registered with baseline {pred['risk_level']} risk assessment!", "success")
                return redirect(url_for("portal.patient_portal", patient_id=new_pid))

            elif action == "add_prescription":
                patient_id = int(request.form.get("patient_id"))
                doctor_id = int(request.form.get("doctor_id"))
                med_name = request.form.get("medication_name", "").strip()
                dosage = request.form.get("dosage", "").strip()
                frequency = request.form.get("frequency", "").strip()
                duration = int(request.form.get("treatment_duration_days", 30))
                instructions = request.form.get("instructions", "").strip()
                start_date = request.form.get("start_date") or date.today().isoformat()

                from datetime import datetime as dt, timedelta as td
                end_date = (dt.strptime(start_date, "%Y-%m-%d") + td(days=duration)).strftime("%Y-%m-%d")

                execute_db(
                    """INSERT INTO prescriptions 
                       (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, end_date, treatment_duration_days, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active');""",
                    (patient_id, doctor_id, med_name, dosage, frequency, instructions, start_date, end_date, duration),
                )
                from app.routes_api import update_patient_risk_assessment
                update_patient_risk_assessment(patient_id)
                flash(f"Prescription '{med_name}' created and patient risk updated!", "success")
                return redirect(url_for("portal.patient_portal", patient_id=patient_id))

            elif action == "add_follow_up":
                patient_id = int(request.form.get("patient_id"))
                doctor_id = int(request.form.get("doctor_id"))
                appt_date = request.form.get("appointment_date")
                notes = request.form.get("notes", "").strip()

                execute_db(
                    """INSERT INTO follow_up_schedules (patient_id, doctor_id, appointment_date, status, notes)
                       VALUES (?, ?, ?, 'Scheduled', ?);""",
                    (patient_id, doctor_id, appt_date, notes),
                )
                flash(f"Follow-up appointment scheduled for {appt_date}!", "success")
                return redirect(url_for("portal.patient_portal", patient_id=patient_id))

            elif action == "add_doctor":
                name = request.form.get("name", "").strip()
                specialty = request.form.get("specialty", "").strip()
                email = request.form.get("email", "").strip()
                phone = request.form.get("phone", "").strip() or None

                if not name or not specialty or not email:
                    flash("Doctor name, specialty, and email are required.", "danger")
                    return redirect(url_for("portal.add_data_portal", tab="doctor"))

                existing = query_db("SELECT id FROM doctors WHERE email = ?;", (email,), one=True)
                if existing:
                    flash(f"Doctor with email '{email}' already exists.", "danger")
                    return redirect(url_for("portal.add_data_portal", tab="doctor"))

                new_did = execute_db(
                    "INSERT INTO doctors (name, specialty, email, phone) VALUES (?, ?, ?, ?);",
                    (name, specialty, email, phone),
                )
                flash(f"Physician '{name}' ({specialty}) registered successfully!", "success")
                return redirect(url_for("portal.doctor_portal", doctor_id=new_did))

            elif action == "log_dose":
                rx_id = int(request.form.get("prescription_id"))
                rx = query_db("SELECT patient_id FROM prescriptions WHERE id = ?;", (rx_id,), one=True)
                if not rx:
                    flash("Prescription not found.", "danger")
                    return redirect(url_for("portal.add_data_portal", tab="adherence"))
                patient_id = rx["patient_id"]
                status = request.form.get("status", "Taken")
                notes = request.form.get("notes", "").strip()

                execute_db(
                    """INSERT INTO adherence_logs (prescription_id, patient_id, scheduled_time, logged_time, status, notes)
                       VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?);""",
                    (rx_id, patient_id, status, notes),
                )
                from app.routes_api import update_patient_risk_assessment
                update_patient_risk_assessment(patient_id)
                flash(f"Medication dose logged as '{status}'!", "success")
                return redirect(url_for("portal.patient_portal", patient_id=patient_id))

        except Exception as e:
            flash(f"Error processing data submission: {str(e)}", "danger")

    return render_template(
        "add_data.html",
        doctors=doctors,
        patients=patients,
        prescriptions=prescriptions,
        active_tab=active_tab,
        today_date=date.today().isoformat(),
    )


@portal_bp.app_context_processor
def inject_current_user():
    """Provides current_user in all Jinja templates."""
    if "user_id" in session:
        return {
            "current_user": {
                "id": session.get("user_id"),
                "username": session.get("username"),
                "email": session.get("email"),
                "role": session.get("role"),
                "full_name": session.get("full_name") or session.get("username"),
                "doctor_id": session.get("doctor_id"),
                "patient_id": session.get("patient_id"),
            }
        }
    return {"current_user": None}


@portal_bp.route("/", methods=["GET", "POST"])
@portal_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Primary Authentication Portal & Default Landing Page.
    Directly renders the login interface at '/' and '/login' for immediate access.
    If already authenticated, redirects directly to their active role portal.
    """
    next_url = request.args.get("next")
    prefill_role = request.args.get("role", "doctor")
    action = request.args.get("action", "login")  # 'login' or 'register'

    # If already logged in and visiting without an action, route directly to their dashboard
    if "user_id" in session and request.method == "GET" and action != "register":
        role = session.get("role")
        if role == "doctor":
            return redirect(url_for("portal.doctor_portal", doctor_id=session.get("doctor_id") or 1))
        elif role == "patient":
            return redirect(url_for("portal.patient_portal", patient_id=session.get("patient_id") or 1))
        elif role == "admin":
            return redirect(url_for("portal.admin_dashboard"))
        return redirect(url_for("portal.overview"))


    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "").strip()
        remember_me = request.form.get("remember_me")
        role_pref = request.form.get("role", prefill_role)

        if not identifier or not password:
            flash("Please enter both your identifier (email or username) and password.", "danger")
            return render_template("login.html", active_role=role_pref, identifier=identifier, next_url=next_url, action="login")

        user = authenticate_user(identifier, password)
        if not user:
            flash("Invalid clinical credentials. Please check your username/email and password, or use one-click demo credentials.", "danger")
            return render_template("login.html", active_role=role_pref, identifier=identifier, next_url=next_url, action="login")

        # Set session
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        session["role"] = user["role"]
        session["full_name"] = user["full_name"]
        session["doctor_id"] = user.get("doctor_id")
        session["patient_id"] = user.get("patient_id")
        if remember_me:
            session.permanent = True

        flash(f"Welcome back, {user['full_name']}! Signed in as {user['role'].capitalize()}.", "success")

        # Route to appropriate portal
        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        if user["role"] == "admin":
            return redirect(url_for("portal.admin_dashboard"))
        elif user["role"] == "doctor":
            doc_id = user.get("doctor_id") or 1
            return redirect(url_for("portal.doctor_portal", doctor_id=doc_id))
        elif user["role"] == "patient":
            pat_id = user.get("patient_id") or 1
            return redirect(url_for("portal.patient_portal", patient_id=pat_id))
        else:
            return redirect(url_for("portal.index"))

    return render_template(
        "login.html",
        active_role=prefill_role,
        action=action,
        next_url=next_url,
    )


@portal_bp.route("/register", methods=["GET", "POST"])
def register():
    """Allows patient or clinician self-registration."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        role = request.form.get("role", "patient").strip()
        extra_field = request.form.get("extra_field", "").strip()

        if not full_name or not email or not username or not password:
            flash("All mandatory fields must be completed.", "danger")
            return redirect(url_for("portal.login", action="register", role=role))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("portal.login", action="register", role=role))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return redirect(url_for("portal.login", action="register", role=role))

        try:
            new_user = register_new_user(
                username=username,
                email=email,
                password=password,
                role=role,
                full_name=full_name,
                extra_field=extra_field,
            )
            # Log in the user
            session.clear()
            session["user_id"] = new_user["id"]
            session["username"] = new_user["username"]
            session["email"] = new_user["email"]
            session["role"] = new_user["role"]
            session["full_name"] = new_user["full_name"]
            session["doctor_id"] = new_user.get("doctor_id")
            session["patient_id"] = new_user.get("patient_id")

            flash(f"Account successfully created! Welcome to HealthGuard, {full_name}.", "success")
            if role == "doctor":
                return redirect(url_for("portal.doctor_portal", doctor_id=new_user["doctor_id"] or 1))
            else:
                return redirect(url_for("portal.patient_portal", patient_id=new_user["patient_id"] or 1))

        except Exception as e:
            flash(str(e), "danger")
            return redirect(url_for("portal.login", action="register", role=role))

    return redirect(url_for("portal.login", action="register"))


@portal_bp.route("/logout")
def logout():
    """Clears user session and redirects to login."""
    user_name = session.get("full_name") or session.get("username") or "User"
    session.clear()
    flash(f"Signed out successfully. Have a healthy day, {user_name}.", "info")
    return redirect(url_for("portal.login"))


