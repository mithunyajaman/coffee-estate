import os
from flask import Flask, render_template, jsonify
from app.config import Config
from app.database import db, migrate
from app.limiter import limiter
from app.services.auth_service import get_current_user

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize database and migration extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize rate limiter
    limiter.init_app(app)

    # Register Blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    # Global context processors for templates
    @app.context_processor
    def inject_global_vars():
        return {
            "current_user": get_current_user(),
            "app_title": "AI-Powered Smart Coffee Estate",
            "estate_location": "Chikmagalur, Karnataka",
        }

    # Custom Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        if app.testing:
            pass
        return (
            render_template(
                "base.html",
                error_code=403,
                error_title="Access Forbidden",
                error_message="You do not have permission to access this resource. Server-side role enforcement blocked this request.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found_error(error):
        return (
            render_template(
                "base.html",
                error_code=404,
                error_title="Page Not Found",
                error_message="The requested estate page or resource could not be found.",
            ),
            404,
        )

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return (
            jsonify({
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please slow down and try again shortly.",
            }),
            429,
        )

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return (
            render_template(
                "base.html",
                error_code=500,
                error_title="System Error",
                error_message="An internal server error occurred. Estate engineers have been notified.",
            ),
            500,
        )

    return app
