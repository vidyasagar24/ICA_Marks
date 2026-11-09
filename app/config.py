import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'academic-assessment-system-super-secret-key-2026')
    
    # Database Configuration: MySQL with SQLite fallback
    # Example MySQL URI: mysql+pymysql://root:password@localhost:3306/academic_assessment_db
    DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'academic_assessment_db')
    
    if os.environ.get('DATABASE_URL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    elif DB_TYPE.lower() == 'mysql':
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
        )
    else:
        sqlite_path = os.path.join(INSTANCE_DIR, 'academic_assessment.db').replace('\\', '/')
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{sqlite_path}"
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    
    # Pagination
    ITEMS_PER_PAGE = 15

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
