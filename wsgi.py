"""
Production WSGI Entry Point (TRD Section 3.1 & 14)
Supports Gunicorn (Linux) and Waitress (Windows Server).
"""
import os
from app import create_app
from app.models import db, User
from seed_data import seed_database

application = create_app()

with application.app_context():
    db.create_all()
    if not User.query.first():
        seed_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    try:
        from waitress import serve
        print(f"Starting Waitress production WSGI server on http://0.0.0.0:{port}...")
        serve(application, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        print(f"Waitress not installed. Starting Flask standard server on port {port}...")
        application.run(host='0.0.0.0', port=port)
