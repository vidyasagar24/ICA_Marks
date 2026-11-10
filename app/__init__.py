from flask import Flask
from app.config import Config
from app.models import db, login_manager, User, AcademicYear

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.faculty import faculty_bp
    from app.routes.reports import reports_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)

    # Context processors
    @app.context_processor
    def inject_global_vars():
        try:
            active_year = AcademicYear.query.filter_by(status='Active').first()
        except Exception:
            db.session.rollback()
            active_year = None
        return {
            'active_academic_year': active_year,
            'app_title': 'Academic Assessment Management System',
            'app_version': '1.0'
        }

    # Index route redirect
    @app.route('/')
    def index():
        from flask import redirect, url_for
        from flask_login import current_user
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('faculty.dashboard'))
        return redirect(url_for('auth.login'))

    def _ensure_db_ready():
        """Fast single-query readiness check; runs create_all + seed only when uninitialized."""
        if getattr(app, '_db_ready', False):
            return
        try:
            if User.query.with_entities(User.id).filter_by(username='admin').first():
                app._db_ready = True
                return
        except Exception:
            # Table likely does not exist yet; reset aborted Postgres transaction before DDL
            db.session.rollback()

        try:
            db.create_all()
            if not User.query.with_entities(User.id).filter_by(username='admin').first():
                from seed_data import seed_database
                seed_database(app=app)
            app._db_ready = True
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Database auto-setup notice: {e}")

    # Ensure database is ready before handling any request (essential for serverless Vercel)
    @app.before_request
    def ensure_database_initialized():
        _ensure_db_ready()

    # Auto-initialize database tables and seed sample data on startup
    with app.app_context():
        _ensure_db_ready()

    return app
