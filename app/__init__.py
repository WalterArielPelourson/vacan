from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager 
from config import Config
# --- PUNTO 1: IMPORTACIÓN PARA CONVENCIÓN DE NOMBRES ---
from sqlalchemy import MetaData 
# ------------------------------------------------------

# 1. Definimos la convención de nombres para evitar errores en SQLite/Alembic
# Esto permite que los nombres de las llaves foráneas y restricciones sean automáticos
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

# 2. Instanciamos las extensiones aquí afuera para que sean accesibles globalmente
# Pasamos la convención a SQLAlchemy (Solución al error "Constraint must have a name")
db = SQLAlchemy(metadata=MetaData(naming_convention=convention))

# IMPORTANTE: Aquí NO pasamos 'app' todavía para evitar el NameError
migrate = Migrate() 

login_manager = LoginManager() 


# --- FUNCIÓN DE AUTO-SINCRONIZACIÓN DE RUBROS/CATEGORÍAS ---
def auto_cargar_categorias():
    from .models import CategoriaMovimiento

    categorias = [
        # --- EGRESOS (Gastos) ---
        ('Logística: Fletes y Envíos', 'EGRESO'),
        ('Logística: Comisionistas', 'EGRESO'),
        ('Logística: Cadetería / Motomensajería', 'EGRESO'),
        ('Personal: Sueldos y Jornales', 'EGRESO'),
        ('Personal: Adelantos y Vales', 'EGRESO'),
        ('Personal: Viáticos y Refrigerios', 'EGRESO'),
        ('Servicios: Luz (EPE/Empresa)', 'EGRESO'),
        ('Servicios: Agua y Gas', 'EGRESO'),
        ('Servicios: Internet y Telefonía', 'EGRESO'),
        ('Local: Alquiler', 'EGRESO'),
        ('Local: Insumos de Oficina / Papelería', 'EGRESO'),
        ('Local: Artículos de Limpieza', 'EGRESO'),
        ('Local: Mantenimiento y Reparaciones', 'EGRESO'),
        ('Impuestos: AFIP (IVA / Monotributo)', 'EGRESO'),
        ('Impuestos: Ingresos Brutos / Tasas', 'EGRESO'),
        ('Financiero: Comisiones Bancarias', 'EGRESO'),
        ('Financiero: Intereses Pagados', 'EGRESO'),
        ('Retiro de Socios / Dueños', 'EGRESO'),
        ('Gastos Varios / Menores', 'EGRESO'),
        ('Retiro de Capital / Inversión', 'EGRESO'),      # <--- DESCOMENTADO Y ACTIVADO
        ('Pago a Proveedores (Mercadería)', 'EGRESO'),
        
        # --- INGRESOS (Entradas Extra) ---
        ('Aporte de Capital / Inversión', 'INGRESO'),
        ('Venta de Rezagos / Chatarra (Cobre/Aluminio)', 'INGRESO'),
        ('Intereses Ganados / Plazo Fijo', 'INGRESO'),
        ('Ajuste de Saldo (+) ', 'INGRESO'),
        ('Cobro de Servicios no Inventariados', 'INGRESO')
    ]

    try:
        hubo_cambios = False
        for nombre, tipo in categorias:
            # Verificamos si ya existe para no duplicar
            existe = CategoriaMovimiento.query.filter_by(nombre=nombre).first()
            if not existe:
                nueva = CategoriaMovimiento(nombre=nombre, tipo=tipo)
                db.session.add(nueva)
                hubo_cambios = True

        if hubo_cambios:
            db.session.commit()
            print("[INFO] Categorías de tesorería sincronizadas con éxito.")
    except Exception as e:
        db.session.rollback()
        # En caso de que la tabla aún no exista durante migraciones iniciales
        print(f"[WARN] No se pudieron sincronizar categorías (aún sin tabla): {e}")





def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 3. Inicializamos las extensiones con la aplicación ya creada
    db.init_app(app)
    
    # --- CAMBIO CRÍTICO PARA PRODUCCIÓN (Punto 2) ---
    # Inicializamos Migrate con el objeto 'app' ya definido y activamos render_as_batch
    migrate.init_app(app, db, render_as_batch=True) 
    # ------------------------------------------------

    # 4. Configuramos el manejador de login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login' 
    login_manager.login_message = "Por favor, inicia sesión para acceder al sistema Vacan."
    login_manager.login_message_category = "info"

    # 5. Importamos los modelos e indicamos cómo cargar al usuario
    from .models import Usuario
    
    @login_manager.user_loader
    def load_user(user_id):
        # Esta función le dice a Flask-Login cómo buscar al usuario en la DB
        return Usuario.query.get(int(user_id))

    # 6. Importamos los Blueprints (Incluyendo la nueva Web Pública)
    from .routes.main import main_bp
    from .routes.inventory import inventory_bp
    from .routes.auth import auth_bp 
    from .routes.admin import admin_bp

    # 7. Registramos las rutas
    app.register_blueprint(main_bp) 
    app.register_blueprint(inventory_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # 8. Auto-sincronización de rubros al arrancar la aplicación
    with app.app_context():
        auto_cargar_categorias()

    return app