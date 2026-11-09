from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User
from app.services.audit_service import log_action

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('faculty.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('auth/login.html')

        from sqlalchemy import func
        user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                return render_template('auth/login.html')

            login_user(user, remember=remember)
            log_action('LOGIN', 'User', entity_id=user.id, updated_value={'username': user.username, 'role': user.role}, user=user)
            
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            if next_page and not next_page.startswith('http'):
                return redirect(next_page)
            
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('faculty.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('LOGOUT', 'User', entity_id=current_user.id, updated_value={'username': current_user.username})
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        curr_pwd = request.form.get('current_password', '')
        new_pwd = request.form.get('new_password', '')
        confirm_pwd = request.form.get('confirm_password', '')

        if not current_user.check_password(curr_pwd):
            flash('Current password does not match.', 'danger')
            return render_template('auth/change_password.html')

        if len(new_pwd) < 6:
            flash('New password must be at least 6 characters.', 'warning')
            return render_template('auth/change_password.html')

        if new_pwd != confirm_pwd:
            flash('New password and confirmation do not match.', 'warning')
            return render_template('auth/change_password.html')

        current_user.set_password(new_pwd)
        db.session.commit()
        log_action('PASSWORD_CHANGE', 'User', entity_id=current_user.id)
        flash('Password updated successfully!', 'success')
        
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('faculty.dashboard'))

    return render_template('auth/change_password.html')
