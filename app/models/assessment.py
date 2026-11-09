from datetime import datetime
from app.models import db

class Assessment(db.Model):
    __tablename__ = 'assessments'

    id = db.Column(db.Integer, primary_key=True)
    mapping_id = db.Column(db.Integer, db.ForeignKey('faculty_subject_mapping.id', ondelete='CASCADE'), nullable=False)
    assessment_name = db.Column(db.String(80), nullable=False)  # 'Test 1', 'Test 2', 'Assignment', 'ICA', 'TEE'
    assessment_type = db.Column(db.String(40), default='Test', nullable=False)
    max_marks = db.Column(db.Float, default=20.0, nullable=False)
    weightage = db.Column(db.Float, default=100.0, nullable=False)
    order_num = db.Column(db.Integer, default=1, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('mapping_id', 'assessment_name', name='uq_mapping_assessment_name'),
    )

    # Relationships
    mapping = db.relationship('FacultySubjectMapping', back_populates='assessments')
    marks = db.relationship('Mark', back_populates='assessment', cascade='all, delete-orphan')
    submissions = db.relationship('Submission', back_populates='assessment', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Assessment {self.assessment_name} (Max: {self.max_marks})>"


class Mark(db.Model):
    __tablename__ = 'marks'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    assessment_id = db.Column(db.Integer, db.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False)
    mapping_id = db.Column(db.Integer, db.ForeignKey('faculty_subject_mapping.id', ondelete='CASCADE'), nullable=False)
    
    score = db.Column(db.Float, nullable=True)  # Null if Absent or Exempted
    status = db.Column(db.String(20), default='Present', nullable=False)  # 'Present', 'Absent', 'Exempted'
    remarks = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'assessment_id', 'mapping_id', name='uq_student_assessment_mapping_mark'),
    )

    # Relationships
    student = db.relationship('Student', back_populates='marks')
    assessment = db.relationship('Assessment', back_populates='marks')
    mapping = db.relationship('FacultySubjectMapping', back_populates='marks')

    @property
    def display_score(self):
        if self.status == 'Absent':
            return 'AB'
        if self.status == 'Exempted':
            return 'EX'
        if self.score is not None:
            # If whole integer, show as int, else round 2 decimals
            return int(self.score) if self.score.is_integer() else round(self.score, 2)
        return '-'

    def __repr__(self):
        return f"<Mark Stu={self.student_id} Ass={self.assessment_id} Score={self.score} Status={self.status}>"


class Submission(db.Model):
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    mapping_id = db.Column(db.Integer, db.ForeignKey('faculty_subject_mapping.id', ondelete='CASCADE'), nullable=False)
    assessment_id = db.Column(db.Integer, db.ForeignKey('assessments.id', ondelete='SET NULL'), nullable=True)  # None means all assessments for mapping
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Workflow status: Draft -> Submitted -> Under Review -> Approved -> Reopened
    status = db.Column(db.String(30), default='Draft', nullable=False)
    submission_date = db.Column(db.DateTime, nullable=True)
    
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    review_date = db.Column(db.DateTime, nullable=True)
    review_comments = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mapping = db.relationship('FacultySubjectMapping', back_populates='submissions')
    assessment = db.relationship('Assessment', back_populates='submissions')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])

    @property
    def badge_class(self):
        classes = {
            'Draft': 'secondary',
            'Submitted': 'primary',
            'Under Review': 'info',
            'Approved': 'success',
            'Reopened': 'warning'
        }
        return classes.get(self.status, 'light')

    def __repr__(self):
        return f"<Submission Mapping={self.mapping_id} Status={self.status}>"
