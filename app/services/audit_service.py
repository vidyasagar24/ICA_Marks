import json
from flask import request
from flask_login import current_user
from app.models import db, AuditLog

def log_action(action, entity_type, entity_id=None, previous_value=None, updated_value=None, user=None):
    """Log user or system actions with before/after state into AuditLog"""
    try:
        user_obj = user or (current_user if current_user.is_authenticated else None)
        user_name = user_obj.username if user_obj else 'System'
        role = user_obj.role if user_obj else 'system'
        user_id = user_obj.id if user_obj else None
        
        # Try to capture client IP
        ip_addr = None
        try:
            if request:
                ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
        except Exception:
            pass

        prev_str = json.dumps(previous_value, default=str) if isinstance(previous_value, (dict, list)) else (str(previous_value) if previous_value is not None else None)
        new_str = json.dumps(updated_value, default=str) if isinstance(updated_value, (dict, list)) else (str(updated_value) if updated_value is not None else None)

        entry = AuditLog(
            user_id=user_id,
            user_name=user_name,
            role=role,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            previous_value=prev_str,
            updated_value=new_str,
            ip_address=ip_addr
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # In case audit log encounters an issue, do not crash the primary transaction
        print(f"Audit log warning: {e}")
