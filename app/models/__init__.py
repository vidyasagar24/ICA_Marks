from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

from app.models.user import User, Faculty, Student, StudentEnrollment
from app.models.academic import AcademicYear, Programme, Semester, Section, Subject
from app.models.mapping import FacultySubjectMapping
from app.models.assessment import Assessment, Mark, Submission
from app.models.audit import AuditLog, MarksAudit

__all__ = [
    'db',
    'login_manager',
    'User',
    'Faculty',
    'Student',
    'StudentEnrollment',
    'AcademicYear',
    'Programme',
    'Semester',
    'Section',
    'Subject',
    'FacultySubjectMapping',
    'Assessment',
    'Mark',
    'Submission',
    'AuditLog',
    'MarksAudit',
]
