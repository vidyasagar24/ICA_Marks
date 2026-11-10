import os
import tempfile

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except Exception:
    pass

# Detect serverless environment (e.g. Vercel, AWS Lambda) where root directory is read-only
IS_SERVERLESS = bool(os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))

if IS_SERVERLESS:
    INSTANCE_DIR = os.path.join(tempfile.gettempdir(), 'academic_assessment_instance')
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
    except Exception:
        INSTANCE_DIR = tempfile.gettempdir()
        
    sqlite_path = os.path.join(INSTANCE_DIR, 'academic_assessment.db').replace('\\', '/')
    bundled_db = os.path.join(BASE_DIR, 'seed', 'academic_assessment.db')
    if (not os.path.exists(sqlite_path) or os.path.getsize(sqlite_path) == 0) and os.path.exists(bundled_db):
        import shutil
        try:
            shutil.copyfile(bundled_db, sqlite_path)
        except Exception:
            pass
else:
    INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
    except Exception:
        INSTANCE_DIR = tempfile.gettempdir()
    sqlite_path = os.path.join(INSTANCE_DIR, 'academic_assessment.db').replace('\\', '/')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'academic-assessment-system-super-secret-key-2026')
    
    # Supabase Configuration
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://fhhksgrxgbhikmoajspe.supabase.co')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_M2Fit8dXdu2uBv02gxsTYg__2QZ53h_')
    SUPABASE_PROJECT_REF = os.environ.get('SUPABASE_PROJECT_REF', 'fhhksgrxgbhikmoajspe')
    
    # Database Configuration: Supabase PostgreSQL / MySQL / SQLite
    DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'academic_assessment_db')
    
    raw_db_url = (
        os.environ.get('DATABASE_URL') or 
        os.environ.get('SUPABASE_DB_URL') or 
        os.environ.get('SUPABASE_DATABASE_URL')
    )
    supabase_db_password = os.environ.get('SUPABASE_DB_PASSWORD')

    # If Supabase password is provided without full URL, construct pooled connection URI
    if not raw_db_url and supabase_db_password:
        pooler_host = os.environ.get('SUPABASE_DB_HOST', f"aws-1-{os.environ.get('SUPABASE_REGION', 'us-east-2')}.pooler.supabase.com")
        raw_db_url = f"postgresql://postgres.{SUPABASE_PROJECT_REF}:{supabase_db_password}@{pooler_host}:6543/postgres?sslmode=require"

    if raw_db_url:
        # Standardize postgres:// -> postgresql:// for SQLAlchemy compatibility
        if raw_db_url.startswith('postgres://'):
            raw_db_url = raw_db_url.replace('postgres://', 'postgresql://', 1)
        
        # Ensure sslmode=require for Supabase remote PostgreSQL connections
        if ('supabase.co' in raw_db_url or 'supabase.com' in raw_db_url) and 'sslmode=' not in raw_db_url:
            delimiter = '&' if '?' in raw_db_url else '?'
            raw_db_url = f"{raw_db_url}{delimiter}sslmode=require"

        SQLALCHEMY_DATABASE_URI = raw_db_url
    elif DB_TYPE.lower() == 'mysql':
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
        )
    else:
        sqlite_path = os.path.join(INSTANCE_DIR, 'academic_assessment.db').replace('\\', '/')
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{sqlite_path}"
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection Pool Management:
    # psycopg2 uses client-side binding (compatible with Supavisor :6543), so a compact QueuePool
    # prevents slow multi-second TLS handshakes on every single query while keeping connections minimal.
    if 'sqlite' in SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_ENGINE_OPTIONS = {}
    elif 'postgresql' in SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 2 if IS_SERVERLESS else 5,
            'max_overflow': 2 if IS_SERVERLESS else 5,
            'pool_recycle': 180 if IS_SERVERLESS else 280,
            'pool_pre_ping': True,
            'connect_args': {'connect_timeout': 10}
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_recycle': 280,
            'pool_pre_ping': True
        }
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    
    # Pagination
    ITEMS_PER_PAGE = 15

try:
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
except Exception:
    pass
