import os
from app import create_app
from app.models import db, User
from seed_data import seed_database

app = create_app()

with app.app_context():
    db.create_all()
    # Check if empty, run seeder automatically
    if not User.query.first():
        print("Empty database detected. Running automatic seeder...")
        seed_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 'yes']
    print("\n" + "="*70)
    print(" ACADEMIC ASSESSMENT MANAGEMENT SYSTEM (AAMS)")
    print(" Faculty Assessment & Student Marks Management System v1.0")
    print("="*70)
    print(f" * Server running on: http://127.0.0.1:{port}/")
    print(" * Admin Login:       admin / Admin@123")
    print(" * Faculty Logins:    faculty_a / Faculty@123  (Dr. Ramesh Sharma)")
    print("                      faculty_b / Faculty@123  (Dr. Priya Sundaram)")
    print("                      faculty_c / Faculty@123  (Prof. Amit Verma)")
    print("="*70 + "\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
