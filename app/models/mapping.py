from datetime import datetime
from app.models import db

class FacultySubjectMapping(db.Model):
    __tablename__ = 'faculty_subject_mapping'

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    programme_id = db.Column(db.Integer, db.ForeignKey('programmes.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    
    status = db.Column(db.String(20), default='Active', nullable=False)  # 'Active', 'Inactive'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'academic_year_id', 'programme_id', 'semester_id', 'section_id', 'subject_id', 'faculty_id',
            name='uq_faculty_subject_section_alloc'
        ),
    )

    # Relationships
    academic_year = db.relationship('AcademicYear', back_populates='mappings')
    programme = db.relationship('Programme', back_populates='mappings')
    semester = db.relationship('Semester', back_populates='mappings')
    section = db.relationship('Section', back_populates='mappings')
    subject = db.relationship('Subject', back_populates='mappings')
    faculty = db.relationship('Faculty', back_populates='mappings')
    
    assessments = db.relationship('Assessment', back_populates='mapping', cascade='all, delete-orphan')
    marks = db.relationship('Mark', back_populates='mapping', cascade='all, delete-orphan')
    submissions = db.relationship('Submission', back_populates='mapping', cascade='all, delete-orphan')

    @property
    def display_title(self):
        return f"{self.subject.subject_code} - {self.subject.subject_name} ({self.programme.code} Sem {self.semester.number} Sec {self.section.name})"

    def __repr__(self):
        return f"<Mapping id={self.id} Subj={self.subject.subject_code} Sec={self.section.name} Fac={self.faculty.name}>"
