from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='faculty')  # 'admin' or 'faculty'
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id', ondelete='SET NULL'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to Faculty profile
    faculty_profile = db.relationship('Faculty', back_populates='user_account', uselist=False, foreign_keys=[faculty_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_faculty_role(self):
        return self.role == 'faculty'

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Faculty(db.Model):
    __tablename__ = 'faculty'

    id = db.Column(db.Integer, primary_key=True)
    faculty_id_code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g., FAC001
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    department = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Active', nullable=False)  # Active / Inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_account = db.relationship('User', back_populates='faculty_profile', uselist=False, foreign_keys='User.faculty_id')
    mappings = db.relationship('FacultySubjectMapping', back_populates='faculty', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Faculty {self.faculty_id_code} - {self.name}>"


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    student_id_code = db.Column(db.String(50), nullable=True)  # System identifier
    register_number = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g. 2026CE001
    student_name = db.Column(db.String(120), nullable=False)
    
    programme_id = db.Column(db.Integer, db.ForeignKey('programmes.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    current_semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=False)
    
    email = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), default='Active', nullable=False)  # Active / Inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    programme = db.relationship('Programme', backref='students')
    academic_year = db.relationship('AcademicYear', backref='students')
    current_semester = db.relationship('Semester', backref='students')
    section = db.relationship('Section', backref='students')
    marks = db.relationship('Mark', back_populates='student', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Student {self.register_number} - {self.student_name}>"


class StudentEnrollment(db.Model):
    __tablename__ = 'student_enrollments'

    enrollment_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    programme_id = db.Column(db.Integer, db.ForeignKey('programmes.id', ondelete='CASCADE'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id', ondelete='CASCADE'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'year_id', 'semester_id', name='uq_student_year_semester_enrollment'),
    )

    # Relationships
    student = db.relationship('Student', backref=db.backref('enrollments', cascade='all, delete-orphan'))
    academic_year = db.relationship('AcademicYear', backref='enrollments')
    programme = db.relationship('Programme', backref='enrollments')
    semester = db.relationship('Semester', backref='enrollments')
    section = db.relationship('Section', backref='enrollments')

    def __repr__(self):
        return f"<Enrollment Stu={self.student_id} Year={self.year_id} Sem={self.semester_id} Sec={self.section_id}>"
