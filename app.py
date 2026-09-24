"""
HealthGuard Platform Main Runner.
Starts the Flask server for web portals and REST APIs.
"""

import os
import sys

# Ensure current directory is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from database.db import init_db
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Ensure database is initialized before launching
    db_file = os.path.join(os.path.dirname(__file__), "healthguard.db")
    if not os.path.exists(db_file):
        print("Database not found. Initializing and seeding...")
        from database.seed_data import seed_database
        seed_database(db_file)

    port = int(os.environ.get("PORT", 5000))
    print(f"============================================================")
    print(f"  HealthGuard: Predictive Patient Follow-Up Platform")
    print(f"  Web Portals & REST API running on http://127.0.0.1:{port}")
    print(f"  - Patient Portal:   http://127.0.0.1:{port}/patient/1")
    print(f"  - Doctor Portal:    http://127.0.0.1:{port}/doctor/1")
    print(f"  - Admin Dashboard:  http://127.0.0.1:{port}/admin")
    print(f"  - ML Risk Sandbox:  http://127.0.0.1:{port}/simulator")
    print(f"  - REST API Docs:    http://127.0.0.1:{port}/api/patients")
    print(f"============================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
