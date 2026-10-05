"""
Streamlit Web Application Companion for HealthGuard.
Provides interactive portals for Patients, Doctors, Admin Dashboard, and ML Simulator.
Run with: streamlit run streamlit_app.py
"""

import os
import sys
import json
import sqlite3
import pandas as pd
import streamlit as st

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from database.db import get_db_connection, query_db, execute_db
from ml.predictor import predict_adherence_risk

st.set_page_config(
    page_title="HealthGuard: Predictive Follow-Up & Adherence Platform",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main { background-color: #0b0f19; color: #f8fafc; }
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); }
    .badge-high { color: #f43f5e; font-weight: bold; background: rgba(244,63,94,0.15); padding: 4px 8px; border-radius: 6px; }
    .badge-med { color: #f59e0b; font-weight: bold; background: rgba(245,158,11,0.15); padding: 4px 8px; border-radius: 6px; }
    .badge-low { color: #10b981; font-weight: bold; background: rgba(16,185,129,0.15); padding: 4px 8px; border-radius: 6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar
st.sidebar.image("https://img.icons8.com/fluency/96/caduceus.png", width=64)
st.sidebar.title("HealthGuard AI")
st.sidebar.caption("Predictive Adherence & Follow-Up")

portal_choice = st.sidebar.radio(
    "Navigation Portal:",
    ["📊 Admin Dashboard", "👨‍⚕️ Doctor Portal", "👤 Patient Portal", "🧪 ML Risk Simulator", "➕ Add New Data"],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**Core Stack:**\n"
    "- Python 3.13\n"
    "- Scikit-Learn Random Forest\n"
    "- SQLite Database\n"
    "- Streamlit & Flask REST API"
)

# -------------------------------------------------------------
# 1. ADMIN DASHBOARD
# -------------------------------------------------------------
if portal_choice == "📊 Admin Dashboard":
    st.title("📊 Hospital Population Adherence & Risk Analytics")
    st.markdown("Monitor population adherence trends and intervene with high-risk patients.")

    total_patients = query_db("SELECT COUNT(*) as c FROM patients;", one=True)["c"]
    total_rx = query_db("SELECT COUNT(*) as c FROM prescriptions WHERE status = 'Active';", one=True)["c"]
    
    adherence_stats = query_db(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken FROM adherence_logs;",
        one=True,
    )
    total_logs = adherence_stats["total"] or 0
    taken_logs = adherence_stats["taken"] or 0
    rate = round((taken_logs / total_logs * 100), 1) if total_logs > 0 else 100.0

    risk_counts = query_db(
        """SELECT r.risk_level, COUNT(*) as count
           FROM risk_assessments r
           INNER JOIN (SELECT patient_id, MAX(id) as max_id FROM risk_assessments GROUP BY patient_id) latest
           ON r.id = latest.max_id
           GROUP BY r.risk_level;"""
    )
    risk_dict = {row["risk_level"]: row["count"] for row in risk_counts}

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monitored Patients", total_patients)
    c2.metric("Overall Adherence Rate", f"{rate}%", delta=f"{rate - 80:.1f}% vs Target")
    c3.metric("Active Prescriptions", total_rx)
    c4.metric("High-Risk Alerts", risk_dict.get("High", 0), delta="Action Required", delta_color="inverse")

    st.markdown("### Risk Stratification & Trends")
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Patient Risk Tier Breakdown")
        df_risk = pd.DataFrame(
            list(risk_dict.items()), columns=["Risk Tier", "Patient Count"]
        )
        st.bar_chart(df_risk.set_index("Risk Tier"))

    with col_chart2:
        st.subheader("7-Day Adherence Trends")
        trend_rows = query_db(
            """SELECT DATE(logged_time) as log_date,
                      SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) as taken,
                      SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as missed
               FROM adherence_logs WHERE logged_time >= DATE('now', '-7 days')
               GROUP BY DATE(logged_time) ORDER BY log_date ASC;"""
        )
        if trend_rows:
            df_trend = pd.DataFrame(trend_rows)
            st.line_chart(df_trend.set_index("log_date")[["taken", "missed"]])

    st.markdown("### ⚠️ High-Risk Patient Intervention Queue")
    high_risk_patients = query_db(
        """SELECT p.name, p.age, p.phone, p.chronic_conditions, d.name as doctor,
                  r.risk_score as confidence_pct, r.recommendations
           FROM patients p
           JOIN doctors d ON p.doctor_id = d.id
           JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC LIMIT 1
           )
           WHERE r.risk_level = 'High';"""
    )
    if high_risk_patients:
        st.dataframe(pd.DataFrame(high_risk_patients), use_container_width=True)
    else:
        st.success("No patients currently in high-risk non-adherence status.")


# -------------------------------------------------------------
# 2. DOCTOR PORTAL
# -------------------------------------------------------------
elif portal_choice == "👨‍⚕️ Doctor Portal":
    st.title("👨‍⚕️ Physician Portal")

    doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY id ASC;")
    doc_map = {f"{d['name']} ({d['specialty']})": d["id"] for d in doctors}
    selected_doc_name = st.selectbox("Select Active Physician:", list(doc_map.keys()))
    doctor_id = doc_map[selected_doc_name]

    risk_filter = st.selectbox("Filter Roster by Adherence Risk:", ["All", "High", "Medium", "Low"])

    query = """
        SELECT p.id, p.name, p.age, p.gender, p.chronic_conditions,
               r.risk_level, r.risk_score, r.recommendations,
               (SELECT COUNT(*) FROM adherence_logs al WHERE al.patient_id = p.id AND al.status = 'Missed') as missed_doses
        FROM patients p
        LEFT JOIN risk_assessments r ON r.id = (
            SELECT id FROM risk_assessments ra WHERE ra.patient_id = p.id ORDER BY evaluated_at DESC LIMIT 1
        )
        WHERE p.doctor_id = ?
    """
    params = [doctor_id]
    if risk_filter != "All":
        query += " AND r.risk_level = ?"
        params.append(risk_filter)

    patients = query_db(query, tuple(params))
    st.subheader(f"Assigned Patients ({len(patients)})")

    if patients:
        df_p = pd.DataFrame(patients)
        st.dataframe(df_p, use_container_width=True)
    else:
        st.info("No patients found for this criteria.")

    # Form to add prescription
    st.markdown("---")
    st.subheader("➕ Prescribe New Medication")
    with st.form("add_rx_form"):
        p_choices = {f"{p['name']} (ID #{p['id']})": p["id"] for p in patients}
        if p_choices:
            rx_patient_label = st.selectbox("Patient:", list(p_choices.keys()))
            rx_patient_id = p_choices[rx_patient_label]
            rx_name = st.text_input("Medication Name:", "Atorvastatin")
            rx_dosage = st.text_input("Dosage:", "20mg")
            rx_freq = st.selectbox("Frequency:", ["Once daily", "Twice daily", "Three times daily", "As needed"])
            rx_dur = st.number_input("Treatment Duration (Days):", min_value=7, max_value=365, value=60)
            rx_instr = st.text_area("Clinical Instructions:", "Take after dinner.")

            submitted = st.form_submit_button("Submit Prescription & Recalculate Risk")
            if submitted:
                execute_db(
                    """INSERT INTO prescriptions 
                       (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, treatment_duration_days, status)
                       VALUES (?, ?, ?, ?, ?, ?, DATE('now'), ?, 'Active');""",
                    (rx_patient_id, doctor_id, rx_name, rx_dosage, rx_freq, rx_instr, rx_dur),
                )
                st.success(f"Prescription for {rx_name} successfully recorded!")
                st.rerun()


# -------------------------------------------------------------
# 3. PATIENT PORTAL
# -------------------------------------------------------------
elif portal_choice == "👤 Patient Portal":
    st.title("👤 Patient Medication & Follow-Up Portal")

    patients = query_db("SELECT id, name, age FROM patients ORDER BY id ASC;")
    pat_map = {f"{p['name']} (Age {p['age']})": p["id"] for p in patients}
    selected_pat = st.selectbox("Select Patient Profile:", list(pat_map.keys()))
    patient_id = pat_map[selected_pat]

    # Patient info
    pat_info = query_db(
        "SELECT p.*, d.name as doctor_name FROM patients p JOIN doctors d ON p.doctor_id = d.id WHERE p.id = ?;",
        (patient_id,),
        one=True,
    )
    risk_info = query_db(
        "SELECT * FROM risk_assessments WHERE patient_id = ? ORDER BY evaluated_at DESC LIMIT 1;",
        (patient_id,),
        one=True,
    )

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown(f"### {pat_info['name']}")
        st.write(f"**Age:** {pat_info['age']} | **Gender:** {pat_info['gender']}")
        st.write(f"**Conditions:** {pat_info['chronic_conditions']}")
        st.write(f"**Attending Physician:** {pat_info['doctor_name']}")
    with col_p2:
        r_level = risk_info["risk_level"] if risk_info else "Low"
        st.metric("Predicted Adherence Risk (ML)", f"{r_level} Risk", f"{risk_info['risk_score'] if risk_info else 95}% Confidence")
        st.caption(risk_info["recommendations"] if risk_info else "Standard care protocol.")

    st.markdown("---")
    st.subheader("Active Prescriptions & Daily Intake")
    rx_list = query_db("SELECT * FROM prescriptions WHERE patient_id = ? AND status = 'Active';", (patient_id,))

    for rx in rx_list:
        with st.container():
            c_r1, c_r2, c_r3 = st.columns([3, 1, 1])
            with c_r1:
                st.markdown(f"**{rx['medication_name']}** — {rx['dosage']} ({rx['frequency']})")
                st.caption(f"Instructions: {rx['instructions'] or 'Take as directed'}")
            with c_r2:
                if st.button(f"✅ Taken", key=f"take_{rx['id']}"):
                    execute_db(
                        "INSERT INTO adherence_logs (prescription_id, patient_id, scheduled_time, status) VALUES (?, ?, CURRENT_TIMESTAMP, 'Taken');",
                        (rx["id"], patient_id),
                    )
                    st.success("Dose logged as Taken!")
                    st.rerun()
            with c_r3:
                if st.button(f"❌ Missed", key=f"miss_{rx['id']}"):
                    execute_db(
                        "INSERT INTO adherence_logs (prescription_id, patient_id, scheduled_time, status) VALUES (?, ?, CURRENT_TIMESTAMP, 'Missed');",
                        (rx["id"], patient_id),
                    )
                    st.warning("Dose logged as Missed!")
                    st.rerun()

    st.markdown("---")
    st.subheader("Upcoming Follow-Up Appointments")
    fu_list = query_db("SELECT appointment_date, status, notes FROM follow_up_schedules WHERE patient_id = ?;", (patient_id,))
    if fu_list:
        st.dataframe(pd.DataFrame(fu_list), use_container_width=True)
    else:
        st.info("No upcoming follow-up appointments scheduled.")


# -------------------------------------------------------------
# 4. ML RISK SIMULATOR
# -------------------------------------------------------------
elif portal_choice == "🧪 ML Risk Simulator":
    st.title("🧪 Predictive Adherence Risk Simulator")
    st.markdown("Adjust clinical features to test the Random Forest model in real time.")

    col_sim_in, col_sim_out = st.columns([1, 1])

    with col_sim_in:
        st.subheader("Input Clinical Variables")
        age = st.slider("Patient Age", 18, 95, 62)
        past_missed_doses = st.slider("Past Missed Doses (Last 30 Days)", 0, 15, 3)
        past_missed_appts = st.slider("Past Missed Appointments", 0, 5, 1)
        treatment_duration = st.slider("Treatment Regimen Duration (Days)", 7, 365, 90)
        num_meds = st.slider("Number of Active Medications (Polypharmacy)", 1, 9, 4)

    with col_sim_out:
        st.subheader("ML Risk Inference Result")
        pred = predict_adherence_risk(
            age=age,
            past_missed_doses=past_missed_doses,
            past_missed_appointments=past_missed_appts,
            treatment_duration_days=treatment_duration,
            num_medications=num_meds,
        )

        r_level = pred["risk_level"]
        color = "red" if r_level == "High" else ("orange" if r_level == "Medium" else "green")
        st.markdown(f"### Predicted Risk Level: :{color}[{r_level} Risk]")
        st.metric("Model Confidence", f"{pred['confidence']}%")

        st.markdown("#### Class Probabilities")
        probs_df = pd.DataFrame([pred["probabilities"]])
        st.bar_chart(probs_df.T)

        st.markdown("#### Clinical Intervention Protocol")
        st.info(pred["recommendations"])


# -------------------------------------------------------------
# 5. ADD NEW DATA
# -------------------------------------------------------------
elif portal_choice == "➕ Add New Data":
    st.title("➕ Add Clinical Data & Patient Records")
    st.markdown("Register new patients, onboard physicians, prescribe medications, or schedule clinical appointments.")

    data_type = st.radio(
        "Select Record Type to Add:",
        ["👤 New Patient", "💊 New Prescription", "📅 Follow-Up Appointment", "👨‍⚕️ New Physician"],
        horizontal=True,
    )

    if data_type == "👤 New Patient":
        st.subheader("Register New Patient Profile")
        with st.form("form_st_patient"):
            c_p1, c_p2 = st.columns(2)
            with c_p1:
                p_name = st.text_input("Full Name:", "Eleanor Vance")
                p_age = st.number_input("Age:", min_value=0, max_value=125, value=58)
                p_gender = st.selectbox("Gender:", ["Female", "Male", "Other"])
            with c_p2:
                p_email = st.text_input("Email:", "e.vance@example.com")
                p_phone = st.text_input("Phone:", "+1-555-0199")
                docs = query_db("SELECT id, name, specialty FROM doctors ORDER BY name ASC;")
                doc_options = {f"{d['name']} ({d['specialty']})": d["id"] for d in docs}
                p_doc = st.selectbox("Attending Physician:", list(doc_options.keys()) if doc_options else ["None"])

            p_conditions = st.text_input("Chronic Conditions (comma separated):", "Type 2 Diabetes, Hypertension")

            submit_pat = st.form_submit_button("Register Patient & Calculate Baseline Risk")
            if submit_pat:
                if not p_name:
                    st.error("Patient name is required.")
                else:
                    doc_id = doc_options[p_doc] if doc_options and p_doc in doc_options else None
                    new_id = execute_db(
                        """INSERT INTO patients (doctor_id, name, age, gender, phone, email, chronic_conditions)
                           VALUES (?, ?, ?, ?, ?, ?, ?);""",
                        (doc_id, p_name, p_age, p_gender, p_phone, p_email, p_conditions),
                    )
                    # Baseline ML Risk
                    pred = predict_adherence_risk(
                        age=p_age, past_missed_doses=0, past_missed_appointments=0, treatment_duration_days=30, num_medications=1
                    )
                    execute_db(
                        """INSERT INTO risk_assessments (patient_id, risk_level, risk_score, features_json, recommendations)
                           VALUES (?, ?, ?, ?, ?);""",
                        (new_id, pred["risk_level"], pred["confidence"], json.dumps(pred["features"]), pred["recommendations"]),
                    )
                    st.success(f"Patient '{p_name}' successfully created (ID #{new_id}) with baseline risk: {pred['risk_level']} Risk ({pred['confidence']}%)!")

    elif data_type == "💊 New Prescription":
        st.subheader("Issue New Medication Prescription")
        patients = query_db("SELECT id, name, age FROM patients ORDER BY name ASC;")
        doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY name ASC;")
        p_dict = {f"{p['name']} (ID #{p['id']})": p["id"] for p in patients}
        d_dict = {f"{d['name']} ({d['specialty']})": d["id"] for d in doctors}

        if not p_dict:
            st.warning("No patients registered yet. Please register a patient first.")
        else:
            with st.form("form_st_rx"):
                c_rx1, c_rx2 = st.columns(2)
                with c_rx1:
                    sel_p = st.selectbox("Patient:", list(p_dict.keys()))
                    rx_name = st.text_input("Medication Name:", "Metformin ER")
                    rx_dose = st.text_input("Dosage:", "500mg")
                with c_rx2:
                    sel_d = st.selectbox("Prescribing Doctor:", list(d_dict.keys()))
                    rx_freq = st.selectbox("Frequency:", ["Once daily (Morning)", "Once daily (Bedtime)", "Twice daily", "Three times daily", "As needed"])
                    rx_days = st.number_input("Duration (Days):", min_value=1, max_value=365, value=30)

                rx_instr = st.text_area("Instructions:", "Take with food.")
                submit_rx = st.form_submit_button("Submit Prescription & Update Risk")
                if submit_rx:
                    execute_db(
                        """INSERT INTO prescriptions 
                           (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, treatment_duration_days, status)
                           VALUES (?, ?, ?, ?, ?, ?, DATE('now'), ?, 'Active');""",
                        (p_dict[sel_p], d_dict[sel_d], rx_name, rx_dose, rx_freq, rx_instr, rx_days),
                    )
                    st.success(f"Prescription for {rx_name} successfully recorded for {sel_p}!")

    elif data_type == "📅 Follow-Up Appointment":
        st.subheader("Schedule Clinical Appointment")
        patients = query_db("SELECT id, name FROM patients ORDER BY name ASC;")
        doctors = query_db("SELECT id, name, specialty FROM doctors ORDER BY name ASC;")
        p_dict = {f"{p['name']} (ID #{p['id']})": p["id"] for p in patients}
        d_dict = {f"{d['name']} ({d['specialty']})": d["id"] for d in doctors}

        if not p_dict:
            st.warning("No patients registered yet.")
        else:
            with st.form("form_st_fu"):
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    sel_p = st.selectbox("Patient:", list(p_dict.keys()))
                    appt_d = st.date_input("Appointment Date:")
                with c_f2:
                    sel_d = st.selectbox("Doctor:", list(d_dict.keys()))
                    notes = st.text_input("Appointment Purpose / Notes:", "Follow-up & adherence check")

                submit_fu = st.form_submit_button("Schedule Follow-Up")
                if submit_fu:
                    execute_db(
                        """INSERT INTO follow_up_schedules (patient_id, doctor_id, appointment_date, status, notes)
                           VALUES (?, ?, ?, 'Scheduled', ?);""",
                        (p_dict[sel_p], d_dict[sel_d], str(appt_d), notes),
                    )
                    st.success("Appointment successfully scheduled!")

    elif data_type == "👨‍⚕️ New Physician":
        st.subheader("Onboard Medical Specialist")
        with st.form("form_st_doc"):
            d_name = st.text_input("Doctor Name:", "Dr. Jennifer Adams, MD")
            d_spec = st.selectbox("Specialty:", ["Cardiology", "Endocrinology", "Internal Medicine", "Geriatrics", "Pulmonology", "Family Medicine"])
            d_email = st.text_input("Email:", "j.adams@hospital.org")
            d_phone = st.text_input("Phone:", "+1-555-4321")

            submit_doc = st.form_submit_button("Register Physician")
            if submit_doc:
                if not d_name or not d_email:
                    st.error("Name and Email are required.")
                else:
                    execute_db(
                        "INSERT INTO doctors (name, specialty, email, phone) VALUES (?, ?, ?, ?);",
                        (d_name, d_spec, d_email, d_phone),
                    )
                    st.success(f"Physician {d_name} successfully registered!")

