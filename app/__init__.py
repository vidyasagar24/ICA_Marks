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
        active_year = AcademicYear.query.filter_by(status='Active').first()
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

    return app
