from datetime import datetime
from app.models import db

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(60), nullable=False, index=True)
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    entity_id = db.Column(db.String(60), nullable=True)
    previous_value = db.Column(db.Text, nullable=True)
    updated_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.entity_type} by {self.user_name} at {self.timestamp}>"


class MarksAudit(db.Model):
    __tablename__ = 'marks_audit'

    audit_id = db.Column(db.Integer, primary_key=True)
    mark_id = db.Column(db.Integer, db.ForeignKey('marks.id', ondelete='CASCADE'), nullable=False)
    old_marks = db.Column(db.Float, nullable=True)
    new_marks = db.Column(db.Float, nullable=True)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reason = db.Column(db.String(500), nullable=True)

    # Relationships
    mark = db.relationship('Mark', backref=db.backref('audit_history', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[changed_by])

    def __repr__(self):
        return f"<MarksAudit Mark={self.mark_id} Old={self.old_marks} New={self.new_marks}>"
