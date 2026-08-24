from app import create_app, db
from app.models import Usuario, Empresa, Sucursal

app = create_app()

with app.app_context():
    # 1. Crear la base de datos (por si no existe)
    db.create_all()

    # 2. Crear la Empresa principal (VACAN) si no existe
    empresa = Empresa.query.filter_by(nombre="Vacan Radiadores").first()
    if not empresa:
        empresa = Empresa(nombre="Vacan Radiadores", cuit="30-12345678-9")
        db.session.add(empresa)
        db.session.commit()
        print("Empresa 'Vacan Radiadores' creada.")
    else:
        print("La empresa ya existe.")

    # 3. Crear la Sucursal Central si no existe
    sucursal = Sucursal.query.filter_by(nombre="Casa Central").first()
    if not sucursal:
        sucursal = Sucursal(nombre="Casa Central", direccion="Av. Principal 123", empresa_id=empresa.id)
        db.session.add(sucursal)
        db.session.commit()
        print("Sucursal 'Casa Central' creada.")
    else:
        print("La sucursal ya existe.")

    # 4. Crear el Superadmin si no existe
    admin = Usuario.query.filter_by(username="admin_vacan").first()
    if not admin:
        # Usamos la contraseña plana como pediste para esta etapa de desarrollo
        admin = Usuario(
            username="admin_vacan", 
            password_hash="vacan2024", 
            rol="superadmin", 
            sucursal_id=sucursal.id
        )
        db.session.add(admin)
        db.session.commit()
        print("---")
        print("SUPERADMIN CREADO CON ÉXITO")
        print("Usuario: admin_vacan")
        print("Clave: vacan2024")
        print("---")
    else:
        print("El usuario admin_vacan ya existe.")