import os
from flask import Flask, render_template
from flask_cors import CORS


def create_app(test_config=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "healthguard-dev-secret-key-2026"),
        DATABASE=os.environ.get("HEALTHGUARD_DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "healthguard.db"))),
    )

    if test_config:
        app.config.update(test_config)

    # Enable CORS for all API routes so Vercel frontend can communicate seamlessly
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Auto-initialize database & model if running on Render / production and DB doesn't exist
    db_path = app.config["DATABASE"]
    if not os.path.exists(db_path):
        from database.seed_data import seed_database
        try:
            seed_database(db_path)
        except Exception as e:
            app.logger.warning(f"Database auto-seed check: {e}")

    # Register Blueprints
    from app.routes_api import api_bp
    from app.routes_portal import portal_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(portal_bp)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html", message="The requested clinical resource was not found."), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("404.html", message="An unexpected server error occurred. Please contact IT support."), 500

    return app
