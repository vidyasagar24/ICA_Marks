"""
Supabase Connection & Diagnostic Utility
Tests connectivity to Supabase REST API and PostgreSQL database.
"""
import os
import sys
import urllib.request
import json
from app.config import Config

def test_supabase_api():
    print("=" * 65)
    print(" 1. TESTING SUPABASE REST / AUTH API")
    print("=" * 65)
    url = f"{Config.SUPABASE_URL}/auth/v1/health"
    headers = {
        'apikey': Config.SUPABASE_KEY
    }
    print(f" * Target URL: {Config.SUPABASE_URL}")
    print(f" * Project Ref: {Config.SUPABASE_PROJECT_REF}")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(" [OK] Supabase API is REACHABLE and ACTIVE!")
            print(f"      Service: {data.get('name', 'GoTrue')} ({data.get('version', 'v2')})")
            return True
    except Exception as e:
        print(f" [FAIL] Could not connect to Supabase API: {e}")
        return False

def test_supabase_db():
    print("\n" + "=" * 65)
    print(" 2. TESTING SUPABASE POSTGRESQL DATABASE")
    print("=" * 65)
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    if not db_uri or 'sqlite' in db_uri or '[YOUR-PASSWORD]' in db_uri:
        print(" [!] Supabase Database URL is not yet configured with your DB password.")
        print("     Current Fallback: Local SQLite database.")
        print("\n To connect the PostgreSQL database:")
        print("  1. Open your Supabase Dashboard: https://supabase.com/dashboard/project/" + Config.SUPABASE_PROJECT_REF + "/settings/database")
        print("  2. Under 'Connection string' -> 'URI' (Transaction or Session pooler), copy the URI.")
        print("  3. Set DATABASE_URL in your .env file or Vercel Environment Variables:")
        print("     DATABASE_URL=postgresql://postgres." + Config.SUPABASE_PROJECT_REF + ":<YOUR-PASSWORD>@aws-0-<REGION>.pooler.supabase.com:6543/postgres?sslmode=require")
        return False

    print(f" * Testing connection to: {db_uri.split('@')[-1] if '@' in db_uri else db_uri}")
    try:
        from app import create_app
        from app.models import db, User
        from seed_data import seed_database
        
        app = create_app()
        with app.app_context():
            # Test simple query
            with db.engine.connect() as conn:
                from sqlalchemy import text
                res = conn.execute(text("SELECT version();")).fetchone()
                print(" [OK] Successfully connected to PostgreSQL Database!")
                print(f"      Version: {res[0][:60]}...")
            
            # Create schema and seed if needed
            print(" * Ensuring schema & initial tables exist in Supabase...")
            db.create_all()
            if not User.query.filter_by(username='admin').first():
                print(" * Seeding initial admin, faculty, and academic data into Supabase...")
                seed_database(app)
            print(" [OK] Supabase PostgreSQL database is fully initialized and operational!")
            return True
    except Exception as e:
        print(f" [FAIL] Database connection error: {e}")
        return False

if __name__ == '__main__':
    api_ok = test_supabase_api()
    db_ok = test_supabase_db()
    print("\n" + "=" * 65)
    if api_ok:
        print(" SUMMARY: Supabase project credentials are valid and verified.")
    print("=" * 65 + "\n")
