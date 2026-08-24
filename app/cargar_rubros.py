from app import create_app, db
from app.models import CategoriaMovimiento

app = create_app()

def cargar_categorias():
    # Lista de rubros sugeridos para Vacan Radiadores
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

        # --- INGRESOS (Entradas Extra) ---
        ('Aporte de Capital / Inversión', 'INGRESO'),
        ('Venta de Rezagos / Chatarra (Cobre/Aluminio)', 'INGRESO'),
        ('Intereses Ganados / Plazo Fijo', 'INGRESO'),
        ('Ajuste de Saldo (+) ', 'INGRESO'),
        ('Cobro de Servicios no Inventariados', 'INGRESO')
    ]

    with app.app_context():
        print("Iniciando carga de rubros para Vacan...")
        for nombre, tipo in categorias:
            # Verificamos si ya existe para no duplicar
            existe = CategoriaMovimiento.query.filter_by(nombre=nombre).first()
            if not existe:
                nueva = CategoriaMovimiento(nombre=nombre, tipo=tipo)
                db.session.add(nueva)
                print(f"Cargado: {nombre} ({tipo})")
        
        db.session.commit()
        print("------------------------------------------")
        print("¡Rubros cargados exitosamente!")

if __name__ == "__main__":
    cargar_categorias()