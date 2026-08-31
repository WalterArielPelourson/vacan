import os
import time
from app import create_app, db # Importamos db para la inicialización
from app.models import Usuario, Empresa, Sucursal # Importamos modelos necesarios

# Configuración de zona horaria a nivel sistema operativo
# Esto es vital para servidores en el extranjero como PythonAnywhere
os.environ['TZ'] = 'America/Argentina/Buenos_Aires'
if hasattr(time, 'tzset'):
    time.tzset()

app = create_app()

# Crear carpeta de subidas si no existe
if not os.path.exists('uploads'):
    os.makedirs('uploads')

# --- CAMBIO PUNTO 1: INICIALIZACIÓN AUTOMÁTICA DE BASE DE DATOS ---
# Esto se ejecuta cada vez que el servidor arranca. 
# Si las tablas no existen, las crea. Si no hay sucursal, crea la inicial.
with app.app_context():
    db.create_all() # Crea las tablas en vacan.bd si no existen
    
    if not Sucursal.query.first():
        print("⚠️ Base de datos nueva detectada. Creando configuración inicial...")
        
        # 1. Crear Empresa
        emp = Empresa(nombre="VACAN RADIADORES", cuit="30-12345678-9")
        db.session.add(emp)
        db.session.commit()

        # 2. Crear Sucursal Principal (Evita el error en main.py)
        suc = Sucursal(nombre="CASA CENTRAL", empresa_id=emp.id, activo=True)
        db.session.add(suc)
        db.session.commit()

        # 3. Crear Usuario Superadmin para poder entrar
        user = Usuario(
            username="admin", 
            password_hash="1234", 
            rol="superadmin", 
            sucursal_id=suc.id, 
            activo=True
        )
        db.session.add(user)
        db.session.commit()
        print("✅ Configuración exitosa. Usuario: admin | Pass: 1234")

if __name__ == '__main__':
    # El modo debug=True es solo para desarrollo local
    app.run(debug=True)