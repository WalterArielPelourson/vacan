from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

# 1. DECORADOR GENÉRICO PARA ROLES
def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol not in roles:
                flash("No tienes permiso para acceder a esta sección.", "danger")
                return redirect(url_for('inventory.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# 2. HELPER PARA FILTRAR CONSULTAS AUTOMÁTICAMENTE
def sucursal_filter(query, model):
    """
    Si es admin, aplica el filtro de sucursal.
    Si es superadmin, devuelve la consulta completa.
    """
    if current_user.rol == 'admin':
        return query.filter(model.sucursal_id == current_user.sucursal_id)
    return query

# 3. VERIFICADOR DE PROPIEDAD (Para editar/borrar)
def check_owner(obj):
    """
    Verifica si el objeto pertenece a la sucursal del usuario.
    Si no es dueño y no es superadmin, lanza un error 403.
    """
    if current_user.rol == 'superadmin':
        return True
    if hasattr(obj, 'sucursal_id') and obj.sucursal_id == current_user.sucursal_id:
        return True
    abort(403) # Prohibido