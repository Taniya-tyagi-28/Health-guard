"""
Database seeding script for HealthGuard.
Populates SQLite with doctors, patients, prescriptions, adherence logs,
follow-up schedules, and baseline ML risk assessments.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import get_db_connection, init_db
from ml.predictor import predict_adherence_risk


def seed_database(db_path: str = None):
    print("Initializing database schema...")
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Clear existing data in case of re-seed
    try:
        cur.execute("DELETE FROM users;")
    except sqlite3.OperationalError:
        pass
    cur.execute("DELETE FROM risk_assessments;")
    cur.execute("DELETE FROM adherence_logs;")
    cur.execute("DELETE FROM follow_up_schedules;")
    cur.execute("DELETE FROM prescriptions;")
    cur.execute("DELETE FROM patients;")
    cur.execute("DELETE FROM doctors;")
    try:
        cur.execute("DELETE FROM sqlite_sequence;")
    except sqlite3.OperationalError:
        pass

    print("Seeding Doctors...")
    doctors = [
        ("Dr. Sarah Jenkins", "Cardiology", "s.jenkins@healthguard.org", "+1-555-0101"),
        ("Dr. Marcus Chen", "Endocrinology & Internal Medicine", "m.chen@healthguard.org", "+1-555-0102"),
        ("Dr. Elena Rostova", "Neurology & Geriatrics", "e.rostova@healthguard.org", "+1-555-0103"),
    ]
    cur.executemany(
        "INSERT INTO doctors (name, specialty, email, phone) VALUES (?, ?, ?, ?);",
        doctors,
    )

    print("Seeding Patients...")
    # (doctor_id, name, age, gender, phone, email, chronic_conditions)
    patients = [
        (1, "Arthur Pendelton", 72, "Male", "+1-555-1101", "arthur.p@example.com", "Hypertension, Heart Failure"),
        (2, "Maria Gonzalez", 48, "Female", "+1-555-1102", "maria.g@example.com", "Type 2 Diabetes, High Cholesterol"),
        (1, "David Kim", 61, "Male", "+1-555-1103", "david.k@example.com", "Coronary Artery Disease, Hypertension"),
        (3, "Emily Watson", 29, "Female", "+1-555-1104", "emily.w@example.com", "Generalized Epilepsy"),
        (2, "James Miller", 54, "Male", "+1-555-1105", "james.m@example.com", "Diabetic Neuropathy, Obesity"),
        (3, "Robert Vance", 81, "Male", "+1-555-1106", "robert.v@example.com", "Mild Cognitive Impairment, Osteoarthritis"),
        (1, "Clara Higgins", 38, "Female", "+1-555-1107", "clara.h@example.com", "Asthma, Mild Hypertension"),
        (2, "Anita Sharma", 65, "Female", "+1-555-1108", "anita.s@example.com", "Type 2 Diabetes, Chronic Kidney Disease"),
        (3, "Samuel Jackson", 74, "Male", "+1-555-1109", "samuel.j@example.com", "Parkinson's Disease, Hypertension"),
        (1, "Lucas Bennett", 23, "Male", "+1-555-1110", "lucas.b@example.com", "Post-Surgical Infection Care"),
    ]
    cur.executemany(
        """INSERT INTO patients (doctor_id, name, age, gender, phone, email, chronic_conditions)
           VALUES (?, ?, ?, ?, ?, ?, ?);""",
        patients,
    )

    print("Seeding Prescriptions...")
    # patient_id, doctor_id, med_name, dosage, frequency, instructions, duration, status
    prescriptions_data = [
        # Arthur Pendelton (High risk patient)
        (1, 1, "Lisinopril", "20mg", "Once daily (Morning)", "Take with full glass of water", 90, "Active"),
        (1, 1, "Furosemide", "40mg", "Once daily (Morning)", "Monitor fluid intake", 60, "Active"),
        (1, 1, "Carvedilol", "12.5mg", "Twice daily", "Take with meals", 90, "Active"),
        (1, 1, "Atorvastatin", "40mg", "Once daily (Bedtime)", "Avoid grapefruit", 180, "Active"),

        # Maria Gonzalez (Moderate risk)
        (2, 2, "Metformin", "850mg", "Twice daily", "Take with food to minimize GI upset", 90, "Active"),
        (2, 2, "Glipizide", "5mg", "Once daily (Breakfast)", "Take 30 min before meal", 90, "Active"),
        (2, 2, "Rosuvastatin", "10mg", "Once daily (Night)", "Consistent timing", 180, "Active"),

        # David Kim (Low risk)
        (3, 1, "Amlodipine", "5mg", "Once daily", "Take at the same time each morning", 90, "Active"),
        (3, 1, "Aspirin (Low-Dose)", "81mg", "Once daily", "Take after food", 365, "Active"),

        # Emily Watson (High risk - missed doses in epilepsy is critical)
        (4, 3, "Levetiracetam (Keppra)", "500mg", "Twice daily", "Do not abruptly stop taking", 120, "Active"),
        (4, 3, "Lamotrigine", "100mg", "Once daily", "Report any new rashes immediately", 90, "Active"),

        # James Miller (Low risk)
        (5, 2, "Metformin ER", "1000mg", "Once daily (Dinner)", "Swallow whole, do not crush", 90, "Active"),
        (5, 2, "Gabapentin", "300mg", "Three times daily", "May cause drowsiness", 60, "Active"),

        # Robert Vance (High risk - elderly polypharmacy)
        (6, 3, "Donepezil", "10mg", "Once daily (Bedtime)", "Take before sleep", 180, "Active"),
        (6, 3, "Memantine", "10mg", "Twice daily", "Maintain hydration", 180, "Active"),
        (6, 3, "Meloxicam", "7.5mg", "Once daily", "Take with food", 60, "Active"),
        (6, 3, "Pantoprazole", "40mg", "Once daily (Morning)", "Take 30m before breakfast", 90, "Active"),
        (6, 3, "Vitamin D3", "2000 IU", "Once daily", "Take with meal", 180, "Active"),

        # Clara Higgins (Low risk)
        (7, 1, "Fluticasone/Salmeterol", "250/50mcg", "Twice daily", "Rinse mouth after inhalation", 60, "Active"),
        (7, 1, "Albuterol Inhaler", "90mcg", "As needed (PRN)", "Use before exercise or wheezing", 30, "Active"),

        # Anita Sharma (Moderate risk)
        (8, 2, "Linagliptin", "5mg", "Once daily", "Take with or without food", 90, "Active"),
        (8, 2, "Losartan", "50mg", "Once daily", "Check blood pressure weekly", 90, "Active"),

        # Samuel Jackson (High risk)
        (9, 3, "Levodopa/Carbidopa", "100/25mg", "Three times daily", "Avoid high protein meals close to dose", 120, "Active"),
        (9, 3, "Pramipexole", "0.5mg", "Three times daily", "Take at scheduled intervals", 90, "Active"),
        (9, 3, "Amlodipine", "10mg", "Once daily", "Morning dose", 90, "Active"),

        # Lucas Bennett (Low risk)
        (10, 1, "Amoxicillin-Clavulanate", "875mg", "Twice daily", "Complete full 14 day antibiotic course", 14, "Active"),
    ]

    today = date.today()
    for row in prescriptions_data:
        p_id, d_id, med, dosage, freq, instr, dur, stat = row
        start = today - timedelta(days=min(15, dur // 2))
        end = start + timedelta(days=dur)
        cur.execute(
            """INSERT INTO prescriptions
               (patient_id, doctor_id, medication_name, dosage, frequency, instructions, start_date, end_date, treatment_duration_days, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            (p_id, d_id, med, dosage, freq, instr, start.isoformat(), end.isoformat(), dur, stat),
        )

    print("Seeding Adherence Logs (past 10 days history)...")
    # Patient behavior profiles:
    # 1: High risk (misses often)
    # 2: Medium risk (occasionally misses or late)
    # 3: Low risk (very consistent)
    # 4: High risk (missed 5 times)
    # 5: Low risk (missed 0)
    # 6: High risk (forgot 6 doses)
    # 7: Low risk (missed 0)
    # 8: Medium risk (missed 2 doses)
    # 9: High risk (missed 4 doses)
    # 10: Low risk (missed 0)
    cur.execute("SELECT id, patient_id FROM prescriptions WHERE status = 'Active';")
    rx_list = cur.fetchall()

    patient_miss_rates = {
        1: 0.38,  # Arthur (High risk)
        2: 0.18,  # Maria (Medium risk)
        3: 0.02,  # David (Low risk)
        4: 0.40,  # Emily (High risk)
        5: 0.03,  # James (Low risk)
        6: 0.42,  # Robert (High risk)
        7: 0.02,  # Clara (Low risk)
        8: 0.20,  # Anita (Medium risk)
        9: 0.35,  # Samuel (High risk)
        10: 0.05, # Lucas (Low risk)
    }

    import random
    random.seed(101)

    for rx in rx_list:
        rx_id = rx["id"]
        pat_id = rx["patient_id"]
        miss_rate = patient_miss_rates.get(pat_id, 0.1)

        # Generate logs for the last 8 days
        for day_offset in range(8, 0, -1):
            log_date = datetime.now() - timedelta(days=day_offset, hours=random.randint(1, 4))
            r = random.random()
            if r < miss_rate:
                status = "Missed"
                notes = random.choice(["Forgot dose", "Side effects / nausea", "Away from home", "Ran out of medication"])
            elif r < (miss_rate + 0.12):
                status = "Late"
                notes = "Taken 3 hours past scheduled time"
            else:
                status = "Taken"
                notes = "Taken with breakfast / on time"

            cur.execute(
                """INSERT INTO adherence_logs
                   (prescription_id, patient_id, scheduled_time, logged_time, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?);""",
                (rx_id, pat_id, log_date.strftime("%Y-%m-%d 08:00:00"), log_date.strftime("%Y-%m-%d %H:%M:%S"), status, notes),
            )

    print("Seeding Follow-Up Schedules...")
    follow_ups = [
        # Arthur Pendelton (Missed 3 past appointments!)
        (1, 1, (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d 10:00:00"), "Attended", "Routine cardiology follow-up"),
        (1, 1, (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d 10:00:00"), "Missed", "Patient failed to show"),
        (1, 1, (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d 11:30:00"), "Missed", "Rescheduled due to illness"),
        (1, 1, (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d 10:00:00"), "Scheduled", "Urgent hypertension review"),

        # Maria Gonzalez (Missed 1)
        (2, 2, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d 14:00:00"), "Attended", "HbA1c quarterly review"),
        (2, 2, (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d 15:00:00"), "Missed", "Transportation conflict"),
        (2, 2, (datetime.now() + timedelta(days=12)).strftime("%Y-%m-%d 14:30:00"), "Scheduled", "Blood sugar re-evaluation"),

        # David Kim (0 missed)
        (3, 1, (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d 09:00:00"), "Attended", "Post-stent checkup"),
        (3, 1, (datetime.now() + timedelta(days=21)).strftime("%Y-%m-%d 09:00:00"), "Scheduled", "Semi-annual CAD check"),

        # Emily Watson (Missed 2)
        (4, 3, (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d 16:00:00"), "Missed", "Forgot appointment date"),
        (4, 3, (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d 15:00:00"), "Scheduled", "Epilepsy EEG follow-up"),

        # Robert Vance (Missed 3)
        (6, 3, (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d 11:00:00"), "Missed", "Caregiver was unavailable"),
        (6, 3, (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d 11:00:00"), "Scheduled", "Cognitive health check"),

        # Samuel Jackson (Missed 2)
        (9, 3, (datetime.now() - timedelta(days=18)).strftime("%Y-%m-%d 13:00:00"), "Missed", "Mobility issues"),
        (9, 3, (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d 13:00:00"), "Scheduled", "Tremor assessment"),
    ]

    cur.executemany(
        """INSERT INTO follow_up_schedules (patient_id, doctor_id, appointment_date, status, notes)
           VALUES (?, ?, ?, ?, ?);""",
        follow_ups,
    )

    print("Running initial ML Risk Evaluations for all patients...")
    cur.execute("SELECT id, age FROM patients;")
    all_patients = cur.fetchall()

    for p in all_patients:
        p_id = p["id"]
        age = p["age"]

        # Calculate actual counts from DB
        cur.execute(
            "SELECT COUNT(*) FROM adherence_logs WHERE patient_id = ? AND status = 'Missed';",
            (p_id,),
        )
        missed_doses = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM follow_up_schedules WHERE patient_id = ? AND status = 'Missed';",
            (p_id,),
        )
        missed_appts = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*), AVG(treatment_duration_days) FROM prescriptions WHERE patient_id = ? AND status = 'Active';",
            (p_id,),
        )
        rx_stats = cur.fetchone()
        num_meds = max(1, rx_stats[0] or 1)
        duration = int(rx_stats[1] or 60)

        # Run inference using the trained Random Forest model
        prediction_result = predict_adherence_risk(
            age=age,
            past_missed_doses=missed_doses,
            past_missed_appointments=missed_appts,
            treatment_duration_days=duration,
            num_medications=num_meds,
        )

        cur.execute(
            """INSERT INTO risk_assessments
               (patient_id, risk_level, risk_score, features_json, recommendations)
               VALUES (?, ?, ?, ?, ?);""",
            (
                p_id,
                prediction_result["risk_level"],
                prediction_result["confidence"],
                json.dumps(prediction_result["features"]),
                prediction_result["recommendations"],
            ),
        )

    print("Seeding Users & Clinical Authentication Accounts...")
    from app.auth import seed_default_users
    seed_default_users(conn)

    conn.commit()
    conn.close()
    print("Database seeding completed successfully with realistic clinical data.")


if __name__ == "__main__":
    seed_database()
