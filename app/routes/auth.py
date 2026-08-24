from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required
from app.models import Usuario
from werkzeug.security import check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Buscamos al usuario en la base de datos de Vacan
        user = Usuario.query.filter_by(username=username).first()
        
        # Lógica de validación: comparamos la contraseña
        if user and user.password_hash == password: 
            
            # --- PUNTO 3: VALIDACIÓN DE ESTADO ACTIVO ---
            if not user.activo:
                flash('Tu cuenta está inactiva. Por favor, contacta al Superadmin de Vacan.', 'warning')
                return redirect(url_for('auth.login'))
            # --------------------------------------------

            login_user(user)
            flash(f'¡Bienvenido {user.username}! Acceso concedido.', 'success')
            return redirect(url_for('inventory.index'))
        
        # Si los datos no coinciden
        flash('Usuario o contraseña incorrectos. Intente de nuevo.', 'danger')
        
    return render_template('login.html')




@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente. ¡Hasta pronto!', 'info')
    return redirect(url_for('auth.login'))