from datetime import datetime
from app.models import db

class AcademicYear(db.Model):
    __tablename__ = 'academic_years'

    id = db.Column(db.Integer, primary_key=True)
    year_code = db.Column(db.String(30), unique=True, nullable=False, index=True)  # e.g., '2026-27'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Active', nullable=False)  # 'Active', 'Archived', 'Upcoming'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sections = db.relationship('Section', back_populates='academic_year', cascade='all, delete-orphan')
    mappings = db.relationship('FacultySubjectMapping', back_populates='academic_year', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<AcademicYear {self.year_code} ({self.status})>"


class Programme(db.Model):
    __tablename__ = 'programmes'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # e.g., 'CE', 'CSD', 'CSE', 'IT'
    name = db.Column(db.String(120), nullable=False)  # e.g., 'Computer Engineering'
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sections = db.relationship('Section', back_populates='programme', cascade='all, delete-orphan')
    subjects = db.relationship('Subject', back_populates='programme', cascade='all, delete-orphan')
    mappings = db.relationship('FacultySubjectMapping', back_populates='programme', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Programme {self.code} - {self.name}>"


class Semester(db.Model):
    __tablename__ = 'semesters'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)  # 1 to 8
    name = db.Column(db.String(30), nullable=False)  # e.g. 'Semester II' or 'Semester IV'
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    sections = db.relationship('Section', back_populates='semester', cascade='all, delete-orphan')
    subjects = db.relationship('Subject', back_populates='semester', cascade='all, delete-orphan')
    mappings = db.relationship('FacultySubjectMapping', back_populates='semester', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Semester {self.name}>"


class Section(db.Model):
    __tablename__ = 'sections'

    id = db.Column(db.Integer, primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey('programmes.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    name = db.Column(db.String(20), nullable=False)  # 'A', 'B', etc.
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('programme_id', 'academic_year_id', 'semester_id', 'name', name='uq_programme_year_sem_section'),
    )

    # Relationships
    programme = db.relationship('Programme', back_populates='sections')
    academic_year = db.relationship('AcademicYear', back_populates='sections')
    semester = db.relationship('Semester', back_populates='sections')
    mappings = db.relationship('FacultySubjectMapping', back_populates='section', cascade='all, delete-orphan')

    @property
    def display_name(self):
        return f"{self.programme.code} - Sem {self.semester.number} - Sec {self.name}"

    def __repr__(self):
        return f"<Section {self.display_name}>"


class Subject(db.Model):
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    subject_code = db.Column(db.String(30), nullable=False, index=True)  # e.g. 'CE201'
    subject_name = db.Column(db.String(150), nullable=False)  # e.g. 'Data Structures'
    programme_id = db.Column(db.Integer, db.ForeignKey('programmes.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    credits = db.Column(db.Integer, default=3, nullable=False)
    ica_max = db.Column(db.Float, default=50.0, nullable=False)  # Internal Continuous Assessment
    tee_max = db.Column(db.Float, default=100.0, nullable=False)  # Term End Examination
    status = db.Column(db.String(20), default='Active', nullable=False)  # Active / Inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('subject_code', 'programme_id', 'semester_id', name='uq_subject_prog_sem'),
    )

    # Relationships
    programme = db.relationship('Programme', back_populates='subjects')
    semester = db.relationship('Semester', back_populates='subjects')
    mappings = db.relationship('FacultySubjectMapping', back_populates='subject', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Subject {self.subject_code} - {self.subject_name}>"
