import math
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db 
from app.models import Repuesto, ModeloAuto, Venta, DetalleVenta, Cliente, Proveedor, MovimientoCtaCte, HistorialPrecio, ModeloAuto, Sucursal, Cheque, get_argentina_time
from flask_login import login_required, current_user
from sqlalchemy import or_, and_ # Importamos 'or_' para búsquedas múltiples
from app.models import HistorialPrecio
from flask import jsonify
from app.models import Presupuesto, DetallePresupuesto # Asegúrate de agregar estos a tus imports
from sqlalchemy import or_, and_ # Importante: Agrega este import arriba
from app.utils.security import roles_required, sucursal_filter
from app.utils.security import check_owner
from datetime import datetime, timedelta

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/dashboard')
@inventory_bp.route('/buscar')
@login_required
def index():
    # 1. Leemos el texto y los selectores
    query_texto = request.args.get('q', '').strip()
    f_rubro = request.args.get('rubro')
    f_subrubro = request.args.get('subrubro')
    f_sucursal = request.args.get('sucursal_id', type=int)
    f_stock = request.args.get('stock_status')
    f_vehiculo = request.args.get('modelo_id', type=int)

    # 2. Consulta base
    query = Repuesto.query.outerjoin(Repuesto.autos_compatibles).outerjoin(Repuesto.sucursal)

    # 3. SI HAY TEXTO EN EL BUSCADOR: Filtra por palabras sin borrar los selectores
    if query_texto:
        palabras = query_texto.split()
        filtros_palabras = []
        for p in palabras:
            termino = f"%{p}%"
            condicion = or_(
                Repuesto.nombre.ilike(termino),
                Repuesto.sku.ilike(termino),
                Repuesto.sku_vacan.ilike(termino),
                Repuesto.codigo_oem.ilike(termino),
                Repuesto.rubro.ilike(termino),
                Repuesto.subrubro.ilike(termino),
                Repuesto.ubicacion.ilike(termino),
                Repuesto.sku_denso.ilike(termino),
                Repuesto.sku_cromosol.ilike(termino),
                Repuesto.sku_expoyer.ilike(termino),
                Repuesto.sku_repuestos_jl.ilike(termino),
                Repuesto.sku_facor.ilike(termino),
                Repuesto.sku_altri.ilike(termino),
                Repuesto.sku_rosparts.ilike(termino),
                Repuesto.otros_codigos.ilike(termino),
                ModeloAuto.marca.ilike(termino),
                ModeloAuto.modelo.ilike(termino),
                Sucursal.nombre.ilike(termino)
            )
            filtros_palabras.append(condicion)
        query = query.filter(and_(*filtros_palabras))

    # 4. SI HAY SELECTORES ELEGIDOS: Se aplican en conjunto con el texto
    if f_rubro:
        query = query.filter(Repuesto.rubro == f_rubro)
    if f_subrubro:
        query = query.filter(Repuesto.subrubro == f_subrubro)
    if f_sucursal:
        query = query.filter(Repuesto.sucursal_id == f_sucursal)
    if f_stock == 'disponible':
        query = query.filter(Repuesto.stock > 0)
    elif f_stock == 'agotado':
        query = query.filter(Repuesto.stock <= 0)
    if f_vehiculo:
        query = query.filter(ModeloAuto.id == f_vehiculo)

    repuestos = query.distinct().order_by(Repuesto.id.desc()).all()

    # 5. Listas completas para los dropdowns
    rubros_unicos = [r[0] for r in db.session.query(Repuesto.rubro).distinct().all() if r[0]]
    subrubros_unicos = [s[0] for s in db.session.query(Repuesto.subrubro).distinct().all() if s[0]]
    sucursales = Sucursal.query.filter_by(activo=True).all()
    vehiculos = ModeloAuto.query.order_by(ModeloAuto.marca, ModeloAuto.modelo).all()

    # 6. Enviamos el diccionario "filtros" y "busqueda" para mantener los valores en pantalla
    return render_template('index.html',
                           repuestos=repuestos,
                           rubros_list=rubros_unicos,
                           subrubros_list=subrubros_unicos,
                           sucursales_list=sucursales,
                           vehiculos_list=vehiculos,
                           busqueda=query_texto,
                           filtros={
                               'q': query_texto,
                               'rubro': f_rubro,
                               'subrubro': f_subrubro,
                               'sucursal_id': f_sucursal,
                               'stock_status': f_stock,
                               'modelo_id': f_vehiculo
                           })
    
    
@inventory_bp.route('/repuesto/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_repuesto():
    if current_user.rol not in ['admin', 'superadmin', 'vendedor']:
        flash('No tiene permisos para esta acción.', 'danger')
        return redirect(url_for('inventory.index'))

    if request.method == 'POST':
        # Capturamos todos los campos nuevos y viejos
        nuevo = Repuesto(
            sku=request.form.get('sku').upper(),             # SKU PROVEEDOR
            sku_vacan=request.form.get('sku_vacan').upper(), # SKU MAESTRO (Sugerido)
            codigo_oem=request.form.get('codigo_oem').upper(),
            nombre=request.form.get('nombre').upper(),
            ubicacion=request.form.get('ubicacion'),
            rubro=request.form.get('rubro').upper(),
            subrubro=request.form.get('subrubro').upper(),
            sucursal_id=request.form.get('sucursal_id'),
            proveedor_id=request.form.get('proveedor_id') or None, # <--- ¡AQUÍ SE GUARDA EL PROVEEDOR!# ID de Sucursal
            stock=int(request.form.get('stock') or 0),
            costo=float(request.form.get('costo') or 0),
            precio=float(request.form.get('precio') or 0),
            descripcion=request.form.get('descripcion'),
            # Auxiliares
            sku_denso=request.form.get('sku_denso'),
            sku_cromosol=request.form.get('sku_cromosol'),
            sku_expoyer=request.form.get('sku_expoyer'),
            sku_repuestos_jl=request.form.get('sku_repuestos_jl'),
            sku_facor=request.form.get('sku_facor'),
            sku_altri=request.form.get('sku_altri'),
            sku_rosparts=request.form.get('sku_rosparts'),
            otros_codigos=request.form.get('otros_codigos')
        )

        # Registro de historial inicial
        db.session.add(HistorialPrecio(
            repuesto=nuevo, costo_anterior=0, costo_nuevo=nuevo.costo,
            precio_anterior=0, precio_nuevo=nuevo.precio, usuario_id=current_user.id
        ))

        # Vinculación opcional de vehículos
        modelos_ids = request.form.getlist('modelos')
        for m_id in modelos_ids:
            modelo = ModeloAuto.query.get(m_id)
            if modelo: nuevo.autos_compatibles.append(modelo)

        db.session.add(nuevo)
        db.session.commit()
        flash(f"Repuesto {nuevo.sku} cargado con éxito en sucursal.", "success")
        return redirect(url_for('inventory.index'))

    # LÓGICA GET: Preparamos sugerencias y listas
    sugerencia = generar_proximo_sku_vacan() # La función que busca el último VAC-
    sucursales = Sucursal.query.filter_by(activo=True).all()
    Proveedor.query.filter_by(activo=True).order_by(Proveedor.razon_social).all() # <--- ¡AQUÍ SE CONSULTA!
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.razon_social).all()  # <--- ESTA LÍNEA ES LA QUE FALTA
    modelos = ModeloAuto.query.order_by(ModeloAuto.marca).all()
    
    return render_template('nuevo_repuesto.html', 
                           sugerencia_sku=sugerencia, 
                           sucursales=sucursales,
                           proveedores=proveedores, # <--- ¡AQUÍ SE ENVÍA AL TEMPLATE! 
                           modelos=modelos)


from app.models import Repuesto, ModeloAuto, HistorialPrecio, Sucursal, Proveedor # Asegúrate de importar Proveedor

@inventory_bp.route('/repuesto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_repuesto(id):
    # Solo admin o superadmin pueden editar
    if current_user.rol not in ['admin', 'superadmin', 'vendedor']:
        flash('No tienes permiso para editar productos.', 'danger')
        return redirect(url_for('inventory.index'))
    
    
    repuesto_actual = Repuesto.query.get_or_404(id)
    
    check_owner(repuesto_actual) 
    
    if request.method == 'POST':
        # Capturamos datos clave para la validación y fusión
        nuevo_sku = request.form.get('sku').upper().strip()
        nuevo_proveedor_id = request.form.get('proveedor_id')
        nueva_sucursal_id = request.form.get('sucursal_id')
        nuevo_stock_form = int(request.form.get('stock') or 0)
        
        repuesto_actual.ubicacion = request.form.get('ubicacion')
        
        nuevo_precio = float(request.form.get('precio') or 0)
        nuevo_costo = float(request.form.get('costo') or 0)

        # 1. REGISTRO EN HISTORIAL (Si hubo cambios económicos)
        if repuesto_actual.precio != nuevo_precio or repuesto_actual.costo != nuevo_costo:
            historial = HistorialPrecio(
                repuesto=repuesto_actual,
                costo_anterior=repuesto_actual.costo,
                costo_nuevo=nuevo_costo,
                precio_anterior=repuesto_actual.precio,
                precio_nuevo=nuevo_precio,
                usuario_id=current_user.id 
            )
            db.session.add(historial)

        # --- 2. LÓGICA DE FUSIÓN (MERGE) ---
        # Buscamos si YA EXISTE otro registro con el mismo SKU + PROVEEDOR + SUCURSAL
        existente = Repuesto.query.filter(
            Repuesto.id != id, # Que no sea el mismo que estamos editando
            Repuesto.sku == nuevo_sku,
            Repuesto.proveedor_id == nuevo_proveedor_id,
            Repuesto.sucursal_id == nueva_sucursal_id
        ).first()

        if existente:
            # Sumamos las unidades al registro que ya estaba allí
            existente.stock += nuevo_stock_form
            # Actualizamos costo y precio al valor más reciente del formulario
            existente.costo = nuevo_costo
            existente.precio = nuevo_precio
            
            # ELIMINAMOS el registro que estábamos editando porque ya se fusionó
            db.session.delete(repuesto_actual)
            db.session.commit()
            
            flash(f"El producto ya existía en la sucursal de destino. Se fusionaron los registros. Nuevo stock total: {existente.stock}.", "info")
            return redirect(url_for('inventory.index'))

        # --- 3. ACTUALIZACIÓN NORMAL (Si no hay duplicados) ---
        repuesto_actual.sku = nuevo_sku
        repuesto_actual.proveedor_id = nuevo_proveedor_id
        repuesto_actual.sucursal_id = nueva_sucursal_id
        
        repuesto_actual.costo = nuevo_costo
        repuesto_actual.precio = nuevo_precio
        repuesto_actual.sku_vacan = request.form.get('sku_vacan').upper()
        repuesto_actual.codigo_oem = request.form.get('codigo_oem').upper()
        repuesto_actual.nombre = request.form.get('nombre').upper()
        repuesto_actual.rubro = request.form.get('rubro').upper()
        repuesto_actual.subrubro = request.form.get('subrubro').upper()
        repuesto_actual.descripcion = request.form.get('descripcion')
        repuesto_actual.stock = nuevo_stock_form
        
        # Actualización de Auxiliares
        repuesto_actual.sku_denso = request.form.get('sku_denso')
        repuesto_actual.sku_cromosol = request.form.get('sku_cromosol')
        repuesto_actual.sku_expoyer = request.form.get('sku_expoyer')
        repuesto_actual.sku_repuestos_jl = request.form.get('sku_repuestos_jl')
        repuesto_actual.sku_facor = request.form.get('sku_facor')
        repuesto_actual.sku_altri = request.form.get('sku_altri')
        repuesto_actual.sku_rosparts = request.form.get('sku_rosparts')
        repuesto_actual.otros_codigos = request.form.get('otros_codigos')

        # Actualización de compatibilidad
        modelos_ids = request.form.getlist('modelos')
        repuesto_actual.autos_compatibles = []
        for m_id in modelos_ids:
            modelo = ModeloAuto.query.get(m_id)
            if modelo: repuesto_actual.autos_compatibles.append(modelo)

        db.session.commit()
        flash(f'Radiador {repuesto_actual.sku} actualizado correctamente.', 'success')
        return redirect(url_for('inventory.index'))
    
    # --- LÓGICA GET (Carga de página) ---
    sucursales = Sucursal.query.filter_by(activo=True).all()
    proveedores = Proveedor.query.filter_by(activo=True).all() # <--- AGREGADO: Lista de proveedores
    modelos = ModeloAuto.query.order_by(ModeloAuto.marca).all()
    
    return render_template('editar_repuesto.html', 
                           repuesto=repuesto_actual, 
                           modelos=modelos, 
                           sucursales=sucursales,
                           proveedores=proveedores) # <--- Variable enviada al HTML
    

from sqlalchemy import or_ # Importamos 'or_' para búsquedas múltiples

from sqlalchemy import or_, and_ # <--- Asegúrate de agregar and_ aquí

@inventory_bp.route('/buscar', methods=['GET'])
@login_required
def buscar():
    query = request.args.get('q', '').strip()
    
    if not query:
        return redirect(url_for('inventory.index'))

    # 1. Separamos la búsqueda en palabras individuales para búsqueda "Fuzzy"
    palabras = query.split()

    # 2. Creamos una lista para almacenar las condiciones de cada palabra
    filtros_por_palabra = []

    for p in palabras:
        search_term = f"%{p}%"
        # Para CADA palabra, buscamos en todas las columnas, incluyendo las NUEVAS
        condicion_palabra = or_(
            Repuesto.nombre.ilike(search_term),
            Repuesto.sku.ilike(search_term),       # SKU del Proveedor
            Repuesto.sku_vacan.ilike(search_term), # Código Maestro Vacan (Punto 2)
            Repuesto.codigo_oem.ilike(search_term),
            Repuesto.rubro.ilike(search_term),     # Nuevo campo Clasificación (Punto 2)
            Repuesto.subrubro.ilike(search_term),  # Nuevo campo Clasificación (Punto 2)
            Repuesto.sku_denso.ilike(search_term),
            Repuesto.sku_cromosol.ilike(search_term),
            Repuesto.sku_expoyer.ilike(search_term),
            Repuesto.sku_repuestos_jl.ilike(search_term),
            Repuesto.sku_facor.ilike(search_term),
            Repuesto.sku_altri.ilike(search_term),
            Repuesto.sku_rosparts.ilike(search_term),
            ModeloAuto.marca.ilike(search_term),
            ModeloAuto.modelo.ilike(search_term),
            Repuesto.ubicacion.ilike(search_term),
            Sucursal.nombre.ilike(search_term)      # Buscar por nombre de Sucursal (Punto 2)
        )
        filtros_por_palabra.append(condicion_palabra)

    # 3. Ejecutamos la consulta usando AND para unir todas las palabras
    # Usamos outerjoin con ModeloAuto y Sucursal para no perder datos si no están asignados
    resultados = Repuesto.query.outerjoin(Repuesto.autos_compatibles).outerjoin(Repuesto.sucursal).filter(
        and_(*filtros_por_palabra)
    ).distinct().all()

    # --- LÓGICA DE SALTO A PROVEEDORES (Mantenida sin omitir nada) ---
    if not resultados:
        flash(f"'{query}' no está en el inventario de Vacan. Buscando en proveedores externos...", "info")
        return redirect(url_for('inventory.catalogos_proveedores', q=query))
    # -----------------------------------------------------------------

    return render_template('index.html', repuestos=resultados, busqueda=query)




# --- GESTIÓN DE MATRIZ DE VEHÍCULOS ---

@inventory_bp.route('/modelos')
@login_required
def modelos_lista():
    # Obtenemos todos los modelos ordenados por Marca y luego por Modelo
    todos_los_modelos = ModeloAuto.query.order_by(ModeloAuto.marca, ModeloAuto.modelo).all()
    return render_template('modelos.html', modelos=todos_los_modelos)

@inventory_bp.route('/modelo/nuevo', methods=['POST'])
@login_required
def nuevo_modelo():
    marca = request.form.get('marca').upper().strip()
    modelo = request.form.get('modelo').upper().strip()
    anio_inicio = request.form.get('anio_inicio')
    anio_fin = request.form.get('anio_fin')

    # Validación básica
    if not marca or not modelo:
        flash("Marca y Modelo son obligatorios", "danger")
        return redirect(url_for('inventory.modelos_lista'))

    nuevo = ModeloAuto(
        marca=marca,
        modelo=modelo,
        anio_inicio=int(anio_inicio) if anio_inicio else None,
        anio_fin=int(anio_fin) if anio_fin else None
    )
    db.session.add(nuevo)
    db.session.commit()
    flash(f"Vehículo {marca} {modelo} agregado a la matriz", "success")
    return redirect(url_for('inventory.modelos_lista'))

@inventory_bp.route('/modelo/editar/<int:id>', methods=['POST'])
@login_required
def editar_modelo(id):
    m = ModeloAuto.query.get_or_404(id)
    m.marca = request.form.get('marca').upper().strip()
    m.modelo = request.form.get('modelo').upper().strip()
    m.anio_inicio = request.form.get('anio_inicio')
    m.anio_fin = request.form.get('anio_fin')
    
    db.session.commit()
    flash("Datos del vehículo actualizados", "success")
    return redirect(url_for('inventory.modelos_lista'))

@inventory_bp.route('/modelo/eliminar/<int:id>')
@login_required
def eliminar_modelo(id):
    if current_user.rol not in ['admin', 'superadmin']:
        flash("No tienes permisos para borrar vehículos de la matriz", "danger")
        return redirect(url_for('inventory.modelos_lista'))
        
    m = ModeloAuto.query.get_or_404(id)
    try:
        db.session.delete(m)
        db.session.commit()
        flash("Vehículo eliminado de la matriz", "warning")
    except:
        db.session.rollback()
        flash("No se puede eliminar: este vehículo está vinculado a radiadores en stock", "danger")
    
    return redirect(url_for('inventory.modelos_lista'))




# --- SECCIÓN DE PUNTO DE VENTA (POS) ---

@inventory_bp.route('/pos')
@login_required
def pos():
    recuperar_id = request.args.get('recuperar_id') # Capturamos el ID si viene del reporte o de la lista
    productos = Repuesto.query.filter(Repuesto.stock > 0).all()
    clientes = Cliente.query.filter_by(activo=True).all()
    
    # --- NUEVO: Traemos las cajas de la sucursal actual + las virtuales ---
    cajas = Caja.query.filter(
        (Caja.sucursal_id == current_user.sucursal_id) | (Caja.tipo == 'VIRTUAL')
    ).all()

    # --- RECUPERACIÓN DE PRESUPUESTO PARA EDICIÓN / FACTURACIÓN ---
    presupuesto_recuperado = None
    if recuperar_id:
        p = Presupuesto.query.get(recuperar_id)
        if p:
            items_p = []
            for dp in p.detalles:
                items_p.append({
                    "id": dp.repuesto_id if dp.repuesto_id else f"manual_{dp.id}",
                    "nombre": dp.nombre_item or (dp.repuesto.nombre if dp.repuesto else "Ítem"),
                    "codigo": dp.repuesto.codigo if (dp.repuesto and hasattr(dp.repuesto, 'codigo')) else "",
                    "precio": float(dp.precio_pactado),
                    "cantidad": int(dp.cantidad),
                    "subtotal": float(dp.precio_pactado * dp.cantidad),
                    "stock": dp.repuesto.stock if (dp.repuesto and hasattr(dp.repuesto, 'stock')) else 999
                })

            # Extraemos la razón social y cuit del cliente de forma segura
            cliente_nombre = "Consumidor Final"
            cliente_cuit = ""
            if p.cliente:
                cliente_nombre = getattr(p.cliente, 'razon_social', getattr(p.cliente, 'nombre', 'Consumidor Final'))
                cliente_cuit = getattr(p.cliente, 'cuit', '')

            presupuesto_recuperado = {
                "id": p.id,
                "cliente_id": p.cliente_id,
                "cliente_nombre": cliente_nombre,
                "cuit": cliente_cuit,
                "total": float(p.total),
                "items": items_p
            }
    
    return render_template(
        'pos.html', 
        productos=productos, 
        clientes=clientes, 
        cajas=cajas, 
        recuperar_id=recuperar_id,
        presupuesto_recuperado=presupuesto_recuperado
    )
@inventory_bp.route('/vender', methods=['POST'])
@login_required
def procesar_venta():
    repuesto_id = request.form.get('repuesto_id')
    cantidad = int(request.form.get('cantidad'))
    repuesto = Repuesto.query.get(repuesto_id)
    
    if repuesto and repuesto.stock >= cantidad:
        # AQUI EL PUNTO 3: Guardamos usuario_id y sucursal_id de la sesión actual
        nueva_venta = Venta(
            total=repuesto.precio * cantidad,
            usuario_id=current_user.id,
            sucursal_id=current_user.sucursal_id
        )
        db.session.add(nueva_venta)
        db.session.flush() # Para obtener el ID de la venta antes del commit

        detalle = DetalleVenta(
            venta_id=nueva_venta.id,
            repuesto_id=repuesto.id,
            cantidad=cantidad,
            precio_unitario=repuesto.precio
        )
        
        repuesto.stock -= cantidad # Descontamos del inventario de Vacan
        
        db.session.add(detalle)
        db.session.commit()
        flash(f'Venta de {repuesto.nombre} realizada con éxito', 'success')
    else:
        flash('Error: Stock insuficiente para realizar la venta', 'danger')
        
    return redirect(url_for('inventory.pos'))




from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db 
from app.models import Repuesto, ModeloAuto, Venta, DetalleVenta, Cliente, MovimientoCtaCte
from flask_login import login_required, current_user

# ... (tus otras rutas de index, buscar, etc.) ...



from app.models import Presupuesto, DetallePresupuesto, PagoVenta, Caja, MovimientoFinanciero # Asegúrate de importar estos

@inventory_bp.route('/pos/procesar', methods=['POST'])
@login_required
def procesar_venta_pro():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No se recibieron datos"}), 400

    cliente_id = data.get('cliente_id')
    items = data.get('items')
    destino = data.get('destino') 
    pago_info = data.get('pago', {})

    # Tomamos el total calculado por el frontend (ya incluye intereses si los hubo)
    total_operacion = float(pago_info.get('total_final', 0))

    # =========================================================================
    # NUEVO: EXTRAER DESCUENTO, RECARGO, IVA Y PLAZO DE PAGO
    # Soporta tanto si vienen en la raíz de data como dentro de pago_info
    # =========================================================================
    descuento_val = float(
        data.get('descuento_global') or 
        data.get('descuento_porcentaje') or 
        pago_info.get('descuento_porcentaje', 0.0) or 0.0
    )
    recargo_val = float(
        data.get('recargo_global') or 
        data.get('recargo_porcentaje') or 
        pago_info.get('recargo_porcentaje') or 
        pago_info.get('interes', 0.0) or 0.0
    )
    iva_val = float(
        data.get('iva_porcentaje') or 
        pago_info.get('iva_porcentaje', 21.0) or 21.0
    )
    plazo_val = int(
        data.get('plazo_pago') or 
        pago_info.get('plazo_pago', 0) or 0
    )
    
    try:
        # --- CASO A: PRESUPUESTO (No toca Stock ni Caja) ---
        # --- CASO A: PRESUPUESTO (No toca Stock ni Caja) ---
        if destino == 'PRESUPUESTO':
            # Capturamos el ID si estamos en modo edición
            presupuesto_id = data.get('presupuesto_id') or data.get('presupuesto_id_origen')
            preso_existente = Presupuesto.query.get(presupuesto_id) if presupuesto_id else None

            if preso_existente:
                # 1. MODO EDICIÓN: ACTUALIZAMOS EL PRESUPUESTO EXISTENTE
                preso_actual = preso_existente
                preso_actual.total = total_operacion
                preso_actual.cliente_id = cliente_id
                
                # Vaciamos los detalles viejos para cargar los nuevos
                for d_viejo in preso_actual.detalles:
                    db.session.delete(d_viejo)
                db.session.flush()
            else:
                # 2. MODO NUEVO: CREAMOS PRESUPUESTO DE CERO (Sin argumentos extras que rompan SQLite)
                preso_actual = Presupuesto(
                    total=total_operacion,
                    cliente_id=cliente_id,
                    usuario_id=current_user.id,
                    sucursal_id=current_user.sucursal_id,
                    estado='PENDIENTE'
                )
                db.session.add(preso_actual)
                db.session.flush()

            # Guardamos los ítems en DetallePresupuesto con precio_pactado
            for item in items:
                item_id = str(item['id'])
                es_man = item_id.startswith(('MAN_', 'manual_')) or not item_id.isdigit()
                id_repuesto = None if es_man else int(item_id)
                nombre_item = str(item.get('nombre', 'ÍTEM SIN NOMBRE')).upper()
                
                detalle_p = DetallePresupuesto(
                    presupuesto_id=preso_actual.id,
                    repuesto_id=id_repuesto,
                    nombre_item=nombre_item,
                    cantidad=int(item['cantidad']),
                    precio_pactado=float(item['precio'])
                )
                db.session.add(detalle_p)
            
            db.session.commit()
            return jsonify({
                "status": "ok",
                "tipo": "PRESUPUESTO",
                "presupuesto_id": preso_actual.id,
                "redireccion": url_for('inventory.imprimir_remito', venta_id=preso_actual.id) if hasattr('inventory', 'imprimir_remito') else f"/ventas/imprimir/{preso_actual.id}"
            })
            
            
        # --- CASO B: VENTA REAL (Remito/Factura/Interno) ---
        else:
            metodo_pago = pago_info.get('medio', 'EFECTIVO')
            if destino == 'CTA_CTE':
                metodo_pago = 'CTA_CTE'

            estado_fiscal = 'FACTURADO' if destino == 'FACTURA' else 'PENDIENTE'
            if destino == 'INTERNO':
                estado_fiscal = 'NO_APLICA'

            tipo_comp = 'FACTURA' if destino == 'FACTURA' else ('REMITO' if destino != 'INTERNO' else 'INTERNO')

            # 1. Crear la Venta base (guardando descuento_global, recargo_global, iva y plazo)
            nueva_venta = Venta(
                total=total_operacion,
                cliente_id=cliente_id,
                usuario_id=current_user.id,
                sucursal_id=current_user.sucursal_id,
                tipo_comprobante=tipo_comp,
                metodo_pago=metodo_pago,
                estado_arca=estado_fiscal,
                # 👇 Campos clave para la impresión:
                descuento_global=descuento_val,
                recargo_global=recargo_val,
                iva_porcentaje=iva_val,
                plazo_pago=plazo_val
            )
            db.session.add(nueva_venta)
            db.session.flush() 

            # 2. Procesar cada ítem (Stock y Detalles)
            for item in items:
                es_manual = not str(item['id']).isdigit()
                id_repuesto = None if es_manual else int(item['id'])

                detalle = DetalleVenta(
                    venta_id=nueva_venta.id,
                    repuesto_id=id_repuesto,
                    nombre_item=item.get('nombre', 'Sin nombre'), 
                    cantidad=int(item['cantidad']),
                    precio_unitario=float(item['precio'])
                )
                
                if not es_manual:
                    rep = Repuesto.query.get(id_repuesto)
                    if rep:
                        rep.stock -= int(item['cantidad'])

                db.session.add(detalle)

            # 3. Registrar detalle financiero del pago
            pago_det = PagoVenta(
                venta_id=nueva_venta.id,
                metodo=metodo_pago,
                monto=total_operacion,
                banco=pago_info.get('referencia'),
                cuotas=int(pago_info.get('cuotas', 1)),
                interes=float(pago_info.get('interes', 0))
            )
            db.session.add(pago_det)

            # --- 4. LÓGICA DE TESORERÍA (NUEVO PUNTO 3) ---
            if metodo_pago == 'CTA_CTE':
                # Si es fía, va a la cuenta del cliente
                mov_ctacte = MovimientoCtaCte(
                    cliente_id=cliente_id,
                    venta_id=nueva_venta.id,
                    monto=total_operacion,
                    tipo='DEUDA',
                    sucursal_id=current_user.sucursal_id,
                    descripcion=f"Remito #{nueva_venta.id} - Pendiente Pago"
                )
                db.session.add(mov_ctacte)
            else:
                # Si es pago real, buscamos el "recipiente" de dinero
                if metodo_pago in ['EFECTIVO', 'CHEQUE_FISICO']:
                    # Va a la caja física de la sucursal actual
                    caja_destino = Caja.query.filter_by(sucursal_id=current_user.sucursal_id, tipo='FISICA').first()
                else:
                    # Bancos, tarjetas, transferencias van a la cuenta virtual
                    caja_destino = Caja.query.filter_by(tipo='VIRTUAL').first()

                if caja_destino:
                    mov_fina = MovimientoFinanciero(
                        caja_id=caja_destino.id,
                        monto=total_operacion,
                        tipo='INGRESO',
                        motivo=f"Venta {nueva_venta.tipo_comprobante} #{nueva_venta.id}",
                        metodo_detalle=metodo_pago,
                        usuario_id=current_user.id,
                        venta_id=nueva_venta.id
                    )
                    # Actualizamos saldo de la caja inmediatamente
                    caja_destino.saldo_actual += total_operacion
                    db.session.add(mov_fina)

            db.session.commit()
            return jsonify({"status": "ok", "venta_id": nueva_venta.id, "message": "Operación completada"})

    except Exception as e:
        db.session.rollback()
        print(f"Error procesando en POS: {str(e)}")
        return jsonify({"status": "error", "message": "Fallo interno: " + str(e)}), 500
    
    
    
# Función para generar el código correlativo
# --- FUNCIÓN AUXILIAR PARA EL SKU CORRELATIVO ---
def generar_proximo_sku_vacan():
    # Buscamos el último SKU que empiece con "VAC-"
    ultimo = Repuesto.query.filter(Repuesto.sku.like('VAC-%')).order_by(Repuesto.sku.desc()).first()
    if not ultimo:
        return "VAC-000001"
    try:
        # Extraemos el número, le sumamos 1 y formateamos a 6 dígitos
        partes = ultimo.sku.split('-')
        nuevo_numero = int(partes[1]) + 1
        return f"VAC-{nuevo_numero:06d}"
    except:
        return "VAC-000001"
    
    
    
@inventory_bp.route('/presupuestos')
@login_required
def lista_presupuestos():
    # Solo mostramos los que no han sido convertidos ni borrados
    presupuestos = Presupuesto.query.filter_by(estado='PENDIENTE').order_by(Presupuesto.fecha.desc()).all()
    return render_template('presupuestos.html', presupuestos=presupuestos)


@inventory_bp.route('/presupuesto/<int:id>')
@login_required
def ver_presupuesto(id):
    presupuesto = Presupuesto.query.get_or_404(id)
    return render_template('ver_presupuesto.html', p=presupuesto)

@inventory_bp.route('/presupuesto/eliminar/<int:id>')
@login_required
def eliminar_presupuesto(id):
    p = Presupuesto.query.get_or_404(id)
    p.estado = 'ELIMINADO' # Borrado lógico
    db.session.commit()
    flash("Presupuesto descartado", "info")
    return redirect(url_for('inventory.lista_presupuestos'))

@inventory_bp.route('/presupuesto/convertir/<int:id>')
@login_required
def convertir_a_remito(id):
    p = Presupuesto.query.get_or_404(id)
    
    # Si tiene cliente va a CTA_CTE, si no tiene cliente (anónimo / mostrador) es EFECTIVO
    metodo = 'CTA_CTE' if p.cliente_id else 'EFECTIVO'
    sucursal_id = getattr(current_user, 'sucursal_id', None)

    # 1. Crear la Venta (Remito)
    nueva_venta = Venta(
        total=p.total, 
        cliente_id=p.cliente_id, 
        usuario_id=current_user.id, 
        sucursal_id=sucursal_id,
        tipo_comprobante='REMITO', 
        metodo_pago=metodo, 
        estado_arca='PENDIENTE'
    )
    db.session.add(nueva_venta)
    db.session.flush()

    # 2. Mover detalles y DESCONTAR STOCK (Protegido contra NoneType)
    for dp in p.detalles:
        detalle_v = DetalleVenta(
            venta_id=nueva_venta.id, 
            repuesto_id=dp.repuesto_id, 
            cantidad=dp.cantidad, 
            precio_unitario=dp.precio_pactado
        )
        
        # Descontar stock solo si el repuesto físico existe
        if dp.repuesto and hasattr(dp.repuesto, 'stock') and dp.repuesto.stock is not None:
            dp.repuesto.stock -= dp.cantidad
            
        db.session.add(detalle_v)

    # 3. Impactar Cta Cte SOLO SI EXISTE UN CLIENTE REGISTRADO
    if p.cliente_id:
        mov = MovimientoCtaCte(
            cliente_id=p.cliente_id, 
            venta_id=nueva_venta.id, 
            sucursal_id=sucursal_id,
            monto=p.total, 
            tipo='DEUDA', 
            descripcion=f"Remito #{nueva_venta.id} (ex Presup #{p.id})"
        )
        db.session.add(mov)

    # 4. Marcar presupuesto como usado
    p.estado = 'CONVERTIDO'
    
    db.session.commit()
    flash("Presupuesto convertido en Venta exitosamente", "success")
    return redirect(url_for('inventory.imprimir_comprobante', id=nueva_venta.id, tipo='remito'))
    

#IMPRESION DE REMITO Y COMPROBANTE INTERNO    
@inventory_bp.route('/venta/imprimir/<int:id>/<string:tipo>')
@login_required
def imprimir_comprobante(id, tipo):
    if tipo == 'remito':
        # Buscamos en la tabla de Ventas
        comprobante = Venta.query.get_or_404(id)
        return render_template('print/remito.html', venta=comprobante)
    
    elif tipo == 'recibo' or tipo == 'interno':
        # Buscamos en la tabla de Movimientos (Cobranzas)
        movimiento = MovimientoCtaCte.query.get_or_404(id)
        return render_template('print/recibo.html', m=movimiento)
    
    return "Tipo de comprobante no válido", 400
    
# --- SECCIÓN DE REPORTES ---

@inventory_bp.route('/repuesto/eliminar/<int:id>')
@login_required
def eliminar_repuesto(id):
    if current_user.rol not in ['admin', 'superadmin']:
        flash('No tienes permiso para eliminar productos', 'danger')
        return redirect(url_for('inventory.index'))
    
    repuesto = Repuesto.query.get_or_404(id)
    db.session.delete(repuesto)
    db.session.commit()
    flash('Producto eliminado del sistema', 'warning')
    return redirect(url_for('inventory.index'))

@inventory_bp.route('/ganancias')
@login_required
def ver_ganancias():
    # Solo administradores pueden ver ganancias
    if current_user.rol not in ['admin', 'superadmin']:
        flash('Acceso denegado a reportes financieros', 'danger')
        return redirect(url_for('inventory.index'))
    
    # Filtramos ventas (si es admin de sucursal, solo ve las suyas)
    if current_user.rol == 'admin':
        todas_las_ventas = Venta.query.filter_by(sucursal_id=current_user.sucursal_id).all()
    else:
        todas_las_ventas = Venta.query.all() # Superadmin ve todo
        
    total_dinero = sum(v.total for v in todas_las_ventas)
    return render_template('ganancias.html', ventas=todas_las_ventas, total=total_dinero)



@inventory_bp.route('/repuesto/historial-precios/<int:id>')
@login_required
def historial_precios(id):
    # Buscamos el repuesto por su ID
    repuesto = Repuesto.query.get_or_404(id)
    
    # Enviamos el repuesto al template. 
    # El historial se cargará automáticamente gracias a la relación en el modelo.
    return render_template('historial_precios.html', repuesto=repuesto)




#Acceso a catalogos de proveedores

# Modifica la ruta existente por esta:
@inventory_bp.route('/catalogos-proveedores')
@inventory_bp.route('/catalogos-proveedores/<int:id>')
@login_required
def catalogos_proveedores(id=None):
    repuesto = None
    query_manual = request.args.get('q', '') # Captura la búsqueda si no hay repuesto
    
    if id:
        repuesto = Repuesto.query.get_or_404(id)
    
    return render_template('proveedores.html', repuesto=repuesto, query_manual=query_manual)





@inventory_bp.route('/ventas/gestion')
@login_required
def gestion_ventas():
    # Listado de todas las ventas para administrar
    ventas = Venta.query.order_by(Venta.fecha.desc()).all()
    return render_template('gestion_ventas.html', ventas=ventas)

@inventory_bp.route('/venta/cambiar-fecha/<int:id>', methods=['POST'])
@login_required
def cambiar_fecha_venta(id):
    venta = Venta.query.get_or_404(id)
    nueva_fecha_str = request.form.get('nueva_fecha')
    # Convertir string a objeto datetime
    venta.fecha = datetime.strptime(nueva_fecha_str, '%Y-%m-%dT%H:%M')
    db.session.commit()
    flash("Fecha actualizada correctamente", "success")
    return redirect(url_for('inventory.gestion_ventas'))

@inventory_bp.route('/venta/marcar-facturado/<int:id>')
@login_required
def marcar_facturado(id):
    venta = Venta.query.get_or_404(id)
    venta.estado_arca = 'FACTURADO'
    db.session.commit()
    flash(f"Remito #{id} marcado como facturado", "info")
    return redirect(url_for('inventory.gestion_ventas'))


@inventory_bp.route('/pos/procesar-avanzado', methods=['POST'])
@login_required
def procesar_venta_avanzada():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No se recibieron datos"}), 400

    # ID de presupuesto si viene de una cotización previa
    presupuesto_id = data.get('presupuesto_id') or data.get('presupuesto_id_origen')
    cliente_id = data.get('cliente_id')
    items = data.get('items', [])
    pagos = data.get('pagos', [])
    tipo_comp = data.get('tipo_comprobante', 'REMITO')
    
    # Captura de porcentajes y plazo con compatibilidad de claves
    iva_p = float(data.get('iva_porcentaje', 21.0) if data.get('iva_porcentaje') is not None else 21.0)
    plazo = int(data.get('plazo_pago') or 0)
    recargo_p = float(data.get('recargo_porcentaje') or data.get('recargo_global') or data.get('recargo') or 0.0)
    descuento_p = float(data.get('descuento_porcentaje') or data.get('descuento_global') or data.get('descuento') or 0.0)

    # Identificamos la sucursal del vendedor actual
    sucursal_vendedor = current_user.sucursal_id

    # 1. Cálculo del Total con Ajustes e IVA
    subtotal_items = sum(float(item['precio']) * int(item['cantidad']) for item in items)
    
    neto_con_ajustes = subtotal_items * (1 + (recargo_p / 100))
    neto_con_ajustes = neto_con_ajustes * (1 - (descuento_p / 100))
    
    total_con_iva = neto_con_ajustes * (1 + (iva_p / 100))
    total_venta = round(total_con_iva, 2)
    
    try:
        # 2. Crear el objeto Venta vinculado a la sucursal del vendedor
        # ¡IMPORTANTE!: Se agregan descuento_global y recargo_global para que figuren en la impresión
        nueva_v = Venta(
            total=total_venta,
            cliente_id=cliente_id,
            usuario_id=current_user.id,
            sucursal_id=sucursal_vendedor,  # Se asigna la sucursal del vendedor
            tipo_comprobante=tipo_comp,
            estado_arca='FACTURADO' if tipo_comp == 'FACTURA' else 'PENDIENTE',
            iva_porcentaje=iva_p, 
            plazo_pago=plazo,
            descuento_global=descuento_p,
            recargo_global=recargo_p
        )
        db.session.add(nueva_v)
        db.session.flush() 

        # 3. Procesar los Ítems del Carrito (Lógica de SKU Local y soporte manual)
        for item in items:
            item_id = str(item['id'])
            # Es manual si empieza con 'MAN_', 'manual_' o si NO son solo dígitos
            es_man = item_id.startswith(('MAN_', 'manual_')) or not item_id.isdigit()
            
            id_rep_final = None
            if not es_man:
                # El ítem viene con un ID numérico de la base de datos
                rep_seleccionado = Repuesto.query.get(int(item_id))
                
                if rep_seleccionado:
                    # BUSCAMOS EL MISMO SKU PERO EN LA SUCURSAL DEL VENDEDOR
                    rep_local = Repuesto.query.filter_by(
                        sku=rep_seleccionado.sku, 
                        sucursal_id=sucursal_vendedor
                    ).first()

                    if not rep_local:
                        raise Exception(f"El producto con SKU {rep_seleccionado.sku} no existe cargado en esta sucursal.")

                    # Verificamos stock en el registro LOCAL
                    if rep_local.stock < int(item['cantidad']):
                        raise Exception(f"Stock insuficiente en esta sucursal para {rep_local.nombre} (Disponibilidad: {rep_local.stock})")
                    
                    # Descontamos del registro de la sucursal del vendedor
                    rep_local.stock -= int(item['cantidad'])
                    id_rep_final = rep_local.id

            nombre_item = str(item.get('nombre', 'ÍTEM')).upper()

            db.session.add(DetalleVenta(
                venta_id=nueva_v.id, 
                repuesto_id=id_rep_final,
                nombre_item=nombre_item,
                cantidad=int(item['cantidad']), 
                precio_unitario=float(item['precio']) 
            ))

        # 4. Procesar la Bolsa de Pagos
        total_abonado_real = 0.0
        if pagos:
            for p in pagos:
                if p is None:
                    continue
                
                monto_p = float(p.get('monto', 0))
                medio = p.get('medio')
                caja_id_manual = p.get('caja_id')

                if medio == 'CTA_CTE':
                    desc_cta = f"Venta {tipo_comp} #{nueva_v.id}"
                    if plazo > 0:
                        fecha_venc = (get_argentina_time() + timedelta(days=plazo)).strftime('%d/%m/%Y')
                        desc_cta += f" - VENCE: {fecha_venc}"
                    
                    db.session.add(MovimientoCtaCte(
                        cliente_id=cliente_id, 
                        venta_id=nueva_v.id, 
                        monto=monto_p,
                        tipo='DEUDA', 
                        sucursal_id=sucursal_vendedor,  # Deuda vinculada a la sucursal local
                        descripcion=desc_cta
                    ))
                else:
                    total_abonado_real += monto_p
                    
                    if caja_id_manual:
                        caja_destino = Caja.query.get(caja_id_manual)
                        
                        if caja_destino:
                            caja_destino.saldo_actual += monto_p
                            db.session.add(MovimientoFinanciero(
                                caja_id=caja_destino.id, 
                                monto=monto_p, 
                                tipo='INGRESO',
                                motivo=f"Venta #{nueva_v.id} ({medio})", 
                                metodo_detalle=medio,
                                usuario_id=current_user.id, 
                                venta_id=nueva_v.id
                            ))
                    else:
                        raise Exception(f"No se seleccionó una caja de destino para el pago con {medio}")

                    if medio == 'CHEQUE':
                        d = p.get('cheque_data')
                        if d:
                            db.session.add(Cheque(
                                banco=d.get('banco', 'S/D').upper(), 
                                numero=d.get('numero', '0'), 
                                emisor=d.get('emisor', 'S/D').upper(),
                                monto=monto_p,
                                fecha_vencimiento=datetime.strptime(d.get('vencimiento'), '%Y-%m-%d').date() if d.get('vencimiento') else get_argentina_time().date(),
                                tipo='FISICO', 
                                cliente_id=cliente_id, 
                                venta_id=nueva_v.id, 
                                estado='EN_CARTERA'
                            ))

        # 5. Finalizar Venta
        nueva_v.total_pagado = total_abonado_real
        nueva_v.esta_pagada = (total_abonado_real >= (total_venta - 0.05)) 
        
        # Si la venta provino de un presupuesto, lo marcamos como CONVERTIDO
        if presupuesto_id:
            preso_original = Presupuesto.query.get(presupuesto_id)
            if preso_original:
                preso_original.estado = 'CONVERTIDO'
        
        db.session.commit()
        return jsonify({"status": "ok", "venta_id": nueva_v.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
       
    
    
@inventory_bp.route('/api/buscar-stock-pos')
@login_required
def buscar_stock_pos():
    query = request.args.get('q', '').strip().lower()
    
    # Si la búsqueda es muy corta, no buscamos nada por rendimiento
    if len(query) < 2:
        return jsonify([])

    search_term = f"%{query}%"
    
    # BUSCADOR INTELIGENTE:
    # 1. Filtramos por la sucursal del usuario actual
    # 2. Buscamos por nombre o por SKU
    # 3. Solo traemos productos que tengan stock > 0
    # 4. Limitamos a 20 resultados para que la respuesta sea instantánea
    productos = Repuesto.query.filter(
        Repuesto.sucursal_id == current_user.sucursal_id,
        (Repuesto.nombre.ilike(search_term)) | (Repuesto.sku.ilike(search_term))
    ).filter(Repuesto.stock > 0).limit(20).all()

    return jsonify([{
        'id': p.id,
        'nombre': p.nombre,
        'sku': p.sku,
        'stock': p.stock,
        'precio': p.precio
    } for p in productos])
    
    
    
@inventory_bp.route('/api/presupuesto/<int:id>')
@login_required
def obtener_datos_presupuesto(id):
    p = Presupuesto.query.get_or_404(id)
    # Verificamos que sea de la misma sucursal (seguridad)
    if p.sucursal_id != current_user.sucursal_id and current_user.rol != 'superadmin':
        return jsonify({"status": "error", "message": "No autorizado"}), 403

    detalles = []
    for d in p.detalles:
        detalles.append({
            "id": d.repuesto_id if d.repuesto_id else f"MAN_{d.id}",
            "nombre": d.nombre_item,
            "cantidad": d.cantidad,
            "precio": d.precio_pactado
        })

    return jsonify({
        "id": p.id,
        "cliente_id": p.cliente_id,
        "items": detalles,
        "total": p.total
    })
    
    
    
    
# ---------------------------------------------
# 1. RUTA PARA IMPRIMIR REMITO (VENTA)
# ---------------------------------------------
@inventory_bp.route('/ventas/<int:id>/imprimir')
@login_required
def imprimir_remito(id):
    venta = Venta.query.get_or_404(id)
    # Le pasamos "venta" a la plantilla (se detectará automáticamente como Remito con la 'R')
    return render_template('remito.html', venta=venta)


# ---------------------------------------------
# 2. RUTA PARA IMPRIMIR PRESUPUESTO
# ---------------------------------------------
@inventory_bp.route('/presupuestos/<int:id>/imprimir')
@login_required
def imprimir_presupuesto(id):
    presupuesto = Presupuesto.query.get_or_404(id)
    # Le pasamos "presupuesto" a la plantilla (se detectará automáticamente como Presupuesto con la 'X')
    return render_template('comprobante_impresion.html', presupuesto=presupuesto)


from datetime import datetime, date, timedelta
import json
import io
import csv
from flask import render_template, request, flash, redirect, url_for, Response, make_response
from flask_login import login_required, current_user
from sqlalchemy import func, or_
# Importa tus modelos de base de datos
from app.models import db, Repuesto, DetalleVenta, Venta, Proveedor, Sucursal

@inventory_bp.route('/reportes/pedidos-proveedores', methods=['GET'])
@login_required
def reporte_pedidos_proveedores():
    # 0. Fecha de hoy segura en Argentina
    try:
        from zoneinfo import ZoneInfo
        hoy = datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    except Exception:
        try:
            import pytz
            hoy = datetime.now(pytz.timezone('America/Argentina/Buenos_Aires')).date()
        except Exception:
            hoy = date.today()

    hace_30_dias = hoy - timedelta(days=30)

    # 1. Capturar todos los parámetros de filtros
    fecha_desde_str = request.args.get('fecha_desde', '')
    fecha_hasta_str = request.args.get('fecha_hasta', '')
    proveedor_id = request.args.get('proveedor_id', type=int)
    sucursal_id = request.args.get('sucursal_id', type=int)
    buscar_repuesto = request.args.get('buscar', '').strip()
    solo_comprar = request.args.get('solo_comprar', '0') == '1'
    estado_stock = request.args.get('estado_stock', 'todos')
    ordenar_por = request.args.get('ordenar_por', 'sugerencia_desc')
    
    # NUEVOS FILTROS SOLICITADOS:
    filtro_estacionalidad = request.args.get('filtro_estacionalidad', 'todos') # 'todos', 'alta', 'baja', 'estable', 'sin_movimiento'
    filtro_ventas_periodo = request.args.get('filtro_ventas_periodo', 'todos') # 'todos', 'mayor_cero', 'igual_cero'
    
    # Stock mínimo definido por filtro
    stock_minimo_filtro = request.args.get('stock_minimo_filtro', type=int)

    # Conversión segura de fechas
    try:
        fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date() if fecha_desde_str else hace_30_dias
    except ValueError:
        fecha_desde = hace_30_dias

    try:
        fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date() if fecha_hasta_str else hoy
    except ValueError:
        fecha_hasta = hoy

    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    # 2. Período anterior (Mismas fechas año pasado para comparar estacionalidad)
    try:
        fecha_desde_ant = fecha_desde.replace(year=fecha_desde.year - 1)
        fecha_hasta_ant = fecha_hasta.replace(year=fecha_hasta.year - 1)
    except ValueError:
        fecha_desde_ant = fecha_desde - timedelta(days=365)
        fecha_hasta_ant = fecha_hasta - timedelta(days=365)

    # 3. Ventas período actual por repuesto
    query_ventas_actual = db.session.query(
        DetalleVenta.repuesto_id,
        func.sum(DetalleVenta.cantidad).label('total_vendido')
    ).join(Venta, DetalleVenta.venta_id == Venta.id)\
     .filter(func.date(Venta.fecha) >= fecha_desde)\
     .filter(func.date(Venta.fecha) <= fecha_hasta)

    if sucursal_id:
        query_ventas_actual = query_ventas_actual.filter(Venta.sucursal_id == sucursal_id)

    ventas_actual_dict = {
        row.repuesto_id: int(row.total_vendido or 0)
        for row in query_ventas_actual.group_by(DetalleVenta.repuesto_id).all()
    }

    # 4. Ventas período anterior (año pasado)
    query_ventas_anterior = db.session.query(
        DetalleVenta.repuesto_id,
        func.sum(DetalleVenta.cantidad).label('total_vendido_ant')
    ).join(Venta, DetalleVenta.venta_id == Venta.id)\
     .filter(func.date(Venta.fecha) >= fecha_desde_ant)\
     .filter(func.date(Venta.fecha) <= fecha_hasta_ant)

    if sucursal_id:
        query_ventas_anterior = query_ventas_anterior.filter(Venta.sucursal_id == sucursal_id)

    ventas_anterior_dict = {
        row.repuesto_id: int(row.total_vendido_ant or 0)
        for row in query_ventas_anterior.group_by(DetalleVenta.repuesto_id).all()
    }

    # 5. Consulta base de repuestos
    query_rep = Repuesto.query

    if proveedor_id:
        query_rep = query_rep.filter(Repuesto.proveedor_id == proveedor_id)

    if sucursal_id and hasattr(Repuesto, 'sucursal_id'):
        query_rep = query_rep.filter(Repuesto.sucursal_id == sucursal_id)

    if buscar_repuesto:
        query_rep = query_rep.filter(Repuesto.descripcion.ilike(f"%{buscar_repuesto}%"))

    todos_repuestos = query_rep.all()

    # 6. Procesamiento y filtros de cada repuesto
    items_reporte = []
    total_unidades_comprar = 0
    total_inversion_estimada = 0.0
    conteo_sin_stock = 0
    conteo_bajo_minimo = 0
    conteo_optimo = 0
    conteo_sin_rotacion = 0

    for rep in todos_repuestos:
        stock_actual = int(getattr(rep, 'stock', 0) or 0)
        costo_unit = float(getattr(rep, 'costo', 0.0) or 0.0)
        
        # Stock mínimo: usa el del filtro si se especificó, sino intenta leer del modelo o toma 0
        if stock_minimo_filtro is not None and stock_minimo_filtro >= 0:
            stock_minimo = stock_minimo_filtro
        else:
            stock_minimo = int(getattr(rep, 'stock_minimo', getattr(rep, 'stock_min', 0)) or 0)

        vendidos_periodo = ventas_actual_dict.get(rep.id, 0)
        vendidos_anterior = ventas_anterior_dict.get(rep.id, 0)

        # NUEVO FILTRO: CANTIDAD VENDIDA EN EL PERÍODO (MAYOR A 0 O IGUAL A 0)
        if filtro_ventas_periodo == 'mayor_cero' and vendidos_periodo <= 0:
            continue
        elif filtro_ventas_periodo == 'igual_cero' and vendidos_periodo > 0:
            continue

        # CÁLCULO DE ESTACIONALIDAD
        if vendidos_anterior > 0:
            variacion_pct = round(((vendidos_periodo - vendidos_anterior) / vendidos_anterior) * 100, 1)
        elif vendidos_periodo > 0:
            variacion_pct = 100.0
        else:
            variacion_pct = 0.0

        if vendidos_periodo == 0 and vendidos_anterior == 0:
            tipo_estacionalidad = 'sin_movimiento'
            estacionalidad_badge = 'Sin Movimiento'
            estacionalidad_color = 'secondary'
        elif variacion_pct >= 20.0:
            tipo_estacionalidad = 'alta'
            estacionalidad_badge = 'Alta Demanda'
            estacionalidad_color = 'success'
        elif variacion_pct <= -20.0:
            tipo_estacionalidad = 'baja'
            estacionalidad_badge = 'Baja Demanda'
            estacionalidad_color = 'danger'
        else:
            tipo_estacionalidad = 'estable'
            estacionalidad_badge = 'Estable'
            estacionalidad_color = 'info'

        # NUEVO FILTRO: ESTACIONALIDAD
        if filtro_estacionalidad != 'todos' and tipo_estacionalidad != filtro_estacionalidad:
            continue

        # FILTRO DE ESTADO DE STOCK
        if estado_stock == 'sin_stock' and stock_actual > 0:
            continue
        elif estado_stock == 'bajo_minimo' and stock_actual > stock_minimo:
            continue
        elif estado_stock == 'con_stock' and stock_actual <= 0:
            continue

        # Contadores para KPIs y Gráficos
        if stock_actual <= 0:
            conteo_sin_stock += 1
        elif stock_actual <= stock_minimo:
            conteo_bajo_minimo += 1
        elif vendidos_periodo == 0:
            conteo_sin_rotacion += 1
        else:
            conteo_optimo += 1

        # CÁLCULO DE SUGERENCIA A PEDIR
        # 1. Déficit para alcanzar el mínimo
        deficit_minimo = max(0, stock_minimo - stock_actual)
        
        # 2. Factor ponderado de reposición
        if vendidos_anterior > 0:
            demanda_proyectada = (vendidos_periodo * 0.7) + (vendidos_anterior * 0.3)
        else:
            demanda_proyectada = float(vendidos_periodo)

        sugerencia = math.ceil(deficit_minimo + (demanda_proyectada * 0.5))

        if stock_actual >= (stock_minimo + vendidos_periodo):
            sugerencia = 0

        # Filtro: Solo los que necesitan comprar
        if solo_comprar and sugerencia <= 0:
            continue

        subtotal = sugerencia * costo_unit
        total_unidades_comprar += sugerencia
        total_inversion_estimada += subtotal

        # Nombres seguros
        codigo_disp = getattr(rep, 'codigo', getattr(rep, 'codigo_repuesto', getattr(rep, 'codigo_interno', f"#{rep.id}")))
        nombre_disp = (rep.descripcion or getattr(rep, 'nombre', f"Repuesto #{rep.id}")).strip()

        items_reporte.append({
            'repuesto': rep,
            'repuesto_id': rep.id,
            'codigo_display': codigo_disp,
            'nombre_display': nombre_disp,
            'stock_actual': stock_actual,
            'stock_minimo': stock_minimo,
            'ventas_periodo': vendidos_periodo,
            'ventas_año_ant': vendidos_anterior,
            'variacion_pct': variacion_pct,
            'estacionalidad_badge': estacionalidad_badge,
            'estacionalidad_color': estacionalidad_color,
            'sugerencia_compra': sugerencia,
            'costo_unitario': costo_unit,
            'subtotal_inversion': subtotal
        })

    # 7. ORDENAMIENTO DE RESULTADOS
    if ordenar_por == 'sugerencia_desc':
        items_reporte.sort(key=lambda x: x['sugerencia_compra'], reverse=True)
    elif ordenar_por == 'stock_asc':
        items_reporte.sort(key=lambda x: x['stock_actual'])
    elif ordenar_por == 'costo_desc':
        items_reporte.sort(key=lambda x: x['subtotal_inversion'], reverse=True)
    elif ordenar_por == 'ventas_desc':
        items_reporte.sort(key=lambda x: x['ventas_periodo'], reverse=True)
    elif ordenar_por == 'nombre_asc':
        items_reporte.sort(key=lambda x: x['nombre_display'].lower())

    # 8. PREPARACIÓN DE GRÁFICOS (CHART.JS)
    grafico_estados_json = json.dumps({
        'labels': ['Sin Stock (0)', 'Bajo Mínimo', 'Óptimo', 'Sin Rotación'],
        'data': [conteo_sin_stock, conteo_bajo_minimo, conteo_optimo, conteo_sin_rotacion],
        'colors': ['#dc3545', '#ffc107', '#198754', '#6c757d']
    })

    top_urgentes = sorted(
        [i for i in items_reporte if i['sugerencia_compra'] > 0],
        key=lambda x: x['sugerencia_compra'],
        reverse=True
    )[:8]

    grafico_top_json = json.dumps({
        'labels': [i['nombre_display'][:18] for i in top_urgentes],
        'stock': [i['stock_actual'] for i in top_urgentes],
        'pedir': [i['sugerencia_compra'] for i in top_urgentes]
    })

    # Consulta segura de proveedores y sucursales
    col_prov = next((getattr(Proveedor, c) for c in ['razon_social', 'nombre', 'empresa', 'nombre_fantasia'] if hasattr(Proveedor, c)), None)
    proveedores = Proveedor.query.order_by(col_prov.asc()).all() if col_prov is not None else Proveedor.query.all()

    col_suc = next((getattr(Sucursal, c) for c in ['nombre', 'descripcion'] if hasattr(Sucursal, c)), None) if 'Sucursal' in globals() else None
    sucursales = Sucursal.query.order_by(col_suc.asc()).all() if col_suc is not None else (Sucursal.query.all() if 'Sucursal' in globals() else [])

    return render_template(
        'reportes/sugerencia_pedidos.html',
        items=items_reporte,
        total_articulos=len(items_reporte),
        total_unidades_comprar=total_unidades_comprar,
        total_inversion_estimada=total_inversion_estimada,
        conteo_sin_stock=conteo_sin_stock,
        conteo_bajo_minimo=conteo_bajo_minimo,
        fecha_desde=fecha_desde.strftime('%Y-%m-%d'),
        fecha_hasta=fecha_hasta.strftime('%Y-%m-%d'),
        fecha_desde_ant=fecha_desde_ant.strftime('%Y-%m-%d'),
        fecha_hasta_ant=fecha_hasta_ant.strftime('%Y-%m-%d'),
        hoy=hoy.strftime('%d/%m/%Y'),
        proveedores=proveedores,
        sucursales=sucursales,
        # Parámetros para mantener el estado de los filtros en la vista
        buscar_sel=buscar_repuesto,
        estado_stock_sel=estado_stock,
        stock_minimo_filtro_sel=stock_minimo_filtro if stock_minimo_filtro is not None else '',
        proveedor_id_sel=proveedor_id,
        sucursal_id_sel=sucursal_id,
        ordenar_por_sel=ordenar_por,
        solo_comprar_sel=solo_comprar,
        filtro_estacionalidad_sel=filtro_estacionalidad,
        filtro_ventas_periodo_sel=filtro_ventas_periodo,
        # Gráficos
        grafico_estados_json=grafico_estados_json,
        grafico_top_json=grafico_top_json
    )


# --- RUTAS DE APOYO PARA EXPORTAR E IMPRIMIR EXCLUSIVAMENTE LO SELECCIONADO ---

@inventory_bp.route('/reportes/pedidos-proveedores/imprimir', methods=['POST'])
@login_required
def imprimir_orden_pedido():
    items_json = request.form.get('items_seleccionados_json', '[]')
    proveedor_nombre = request.form.get('proveedor_nombre', 'Proveedor General')
    fecha_pedido = request.form.get('fecha_pedido', date.today().strftime('%d/%m/%Y'))
    
    try:
        items = json.loads(items_json)
    except Exception:
        items = []

    total_unidades = sum(int(it.get('cantidad', 0)) for it in items)
    total_monto = sum(float(it.get('subtotal', 0.0)) for it in items)

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Orden de Compra - Vacan Radiadores</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 25px; color: #222; }}
            .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 20px; }}
            .title {{ font-size: 20px; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; font-size: 13px; }}
            th {{ background-color: #f4f4f4; text-align: left; }}
            .text-end {{ text-align: right; }}
            .text-center {{ text-align: center; }}
            .totales {{ margin-top: 25px; text-align: right; font-size: 15px; font-weight: bold; }}
            .firmas {{ margin-top: 60px; display: flex; justify-content: space-between; }}
            .linea-firma {{ width: 220px; border-top: 1px solid #000; text-align: center; padding-top: 6px; font-size: 12px; }}
            @media print {{ body {{ padding: 0; }} }}
        </style>
    </head>
    <body onload="window.print()">
        <div class="header">
            <div>
                <div class="title">VACAN RADIADORES</div>
                <div>Orden de Compra y Reposición a Proveedor</div>
                <div><strong>Destinatario:</strong> {proveedor_nombre}</div>
            </div>
            <div style="text-align: right; font-size: 13px;">
                <strong>Fecha:</strong> {fecha_pedido}<br>
                <strong>Items Solicitados:</strong> {len(items)}
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th style="width: 15%;">Código</th>
                    <th style="width: 50%;">Descripción / Repuesto</th>
                    <th class="text-center" style="width: 10%;">Cantidad</th>
                    <th class="text-end" style="width: 12%;">Costo Unit.</th>
                    <th class="text-end" style="width: 13%;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
    """
    for it in items:
        html += f"""
                <tr>
                    <td><strong>{it.get('codigo', '')}</strong></td>
                    <td>{it.get('nombre', '')}</td>
                    <td class="text-center"><strong>{it.get('cantidad', 0)}</strong></td>
                    <td class="text-end">${it.get('costo', 0.0):,.2f}</td>
                    <td class="text-end"><strong>${it.get('subtotal', 0.0):,.2f}</strong></td>
                </tr>
        """
    html += f"""
            </tbody>
        </table>

        <div class="totales">
            <div>Total de Piezas a Reponer: {total_unidades}</div>
            <div style="font-size: 18px; margin-top: 5px; color: #0d6efd;">Monto Total Estimado: ${total_monto:,.2f}</div>
        </div>

        <div class="firmas">
            <div class="linea-firma">Firma y Aclaración (Compras)</div>
            <div class="linea-firma">Recepción Proveedor</div>
        </div>
    </body>
    </html>
    """
    return html


@inventory_bp.route('/reportes/pedidos-proveedores/exportar-excel', methods=['POST'])
@login_required
def exportar_pedido_excel():
    items_json = request.form.get('items_seleccionados_json', '[]')
    try:
        items = json.loads(items_json)
    except Exception:
        items = []

    # Generar CSV con BOM para Excel en español
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Código', 'Descripción', 'Cantidad Pedida', 'Costo Unitario', 'Subtotal Estimado'])

    for it in items:
        writer.writerow([
            it.get('codigo', ''),
            it.get('nombre', ''),
            it.get('cantidad', 0),
            f"{it.get('costo', 0.0):.2f}".replace('.', ','),
            f"{it.get('subtotal', 0.0):.2f}".replace('.', ',')
        ])

    csv_data = output.getvalue()
    output.close()

    response = Response(csv_data, mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=Pedido_Proveedores_{date.today().strftime("%Y%m%d")}.csv'
    return response




@inventory_bp.route('/reportes/predictivo-inteligencia', methods=['GET'])
@login_required
def reporte_predictivo_inteligencia():
    hoy = date.today()
    
    # 1. Parámetros de filtros capturados
    escenario = request.args.get('escenario', 'moderado') # 'moderado', 'temporada_alta', 'conservador'
    factor_inflacion = float(request.args.get('factor_inflacion', 0.0) or 0.0)
    sucursal_id = request.args.get('sucursal_id', type=int)

    # Multiplicador de demanda según escenario
    if escenario == 'temporada_alta':
        multiplicador_escenario = 1.25  # +25% demanda proyectada
    elif escenario == 'conservador':
        multiplicador_escenario = 0.85  # -15% demanda
    else:
        multiplicador_escenario = 1.0   # 100% tendencia natural

    # 2. Extracción de Ventas Históricas de los últimos 6 meses (filtradas por sucursal si se seleccionó)
    hace_6_meses = hoy - timedelta(days=180)
    
    query_historico = db.session.query(
        func.strftime('%Y-%m', Venta.fecha).label('mes'),
        func.count(Venta.id).label('cantidad_ventas'),
        func.sum(Venta.total).label('total_facturado')
    ).filter(Venta.fecha >= hace_6_meses)

    if sucursal_id:
        query_historico = query_historico.filter(Venta.sucursal_id == sucursal_id)

    ventas_historicas = query_historico.group_by('mes').order_by('mes').all()

    meses_etiquetas = []
    totales_reales = []
    
    for row in ventas_historicas:
        meses_etiquetas.append(row.mes)
        totales_reales.append(float(row.total_facturado or 0.0))

    if not totales_reales:
        meses_etiquetas = [(hoy - timedelta(days=30*i)).strftime('%Y-%m') for i in reversed(range(1, 4))]
        totales_reales = [0.0, 0.0, 0.0]

    # 3. Algoritmo Predictivo: Regresión Lineal con proyección a 3 meses
    n = len(totales_reales)
    x_vals = list(range(n))
    y_vals = totales_reales
    
    sum_x = sum(x_vals)
    sum_y = sum(y_vals)
    sum_xx = sum(x * x for x in x_vals)
    sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
    
    denominador = (n * sum_xx - sum_x * sum_x)
    if denominador != 0:
        pendiente = (n * sum_xy - sum_x * sum_y) / denominador
        interseccion = (sum_y - pendiente * sum_x) / n
    else:
        pendiente = 0.0
        interseccion = sum_y / max(n, 1)

    etiquetas_proyeccion = list(meses_etiquetas)
    valores_proyectados = list(totales_reales)
    solo_predicciones = [None] * (n - 1) + [totales_reales[-1]]
    
    total_proyectado_30d = 0.0
    total_proyectado_60d = 0.0
    total_proyectado_90d = 0.0

    for i in range(1, 4):
        proximo_x = (n - 1) + i
        estimado = max(0.0, (interseccion + pendiente * proximo_x) * multiplicador_escenario)
        fecha_futura = hoy + timedelta(days=30 * i)
        etiquetas_proyeccion.append(fecha_futura.strftime('%Y-%m'))
        valores_proyectados.append(None)
        solo_predicciones.append(round(estimado, 2))

        if i == 1: total_proyectado_30d = estimado
        if i == 2: total_proyectado_60d = estimado
        if i == 3: total_proyectado_90d = estimado

    # 4. Velocidad de Ventas por Repuesto (Últimos 45 días) filtrada por sucursal
    hace_45_dias = hoy - timedelta(days=45)
    
    query_recientes = db.session.query(
        DetalleVenta.repuesto_id,
        func.sum(DetalleVenta.cantidad).label('cant_vendida')
    ).join(Venta, DetalleVenta.venta_id == Venta.id)\
     .filter(Venta.fecha >= hace_45_dias)

    if sucursal_id:
        query_recientes = query_recientes.filter(Venta.sucursal_id == sucursal_id)

    ventas_ritmo = {row.repuesto_id: float(row.cant_vendida or 0) for row in query_recientes.group_by(DetalleVenta.repuesto_id).all()}

    # Consulta de Repuestos
    query_repuestos = Repuesto.query
    if sucursal_id and hasattr(Repuesto, 'sucursal_id'):
        query_repuestos = query_repuestos.filter(Repuesto.sucursal_id == sucursal_id)

    repuestos_db = query_repuestos.all()
    
    analisis_repuestos = []
    capital_inmovilizado_total = 0.0
    capital_en_riesgo_quiebre = 0.0
    repuestos_criticos_quiebre = 0
    repuestos_inmovilizados = 0

    for r in repuestos_db:
        stock = int(getattr(r, 'stock', 0) or 0)
        costo = float(getattr(r, 'precio_costo', 0) or getattr(r, 'costo', 0) or 0.0)
        stock_min = int(getattr(r, 'stock_minimo', 0) or 0)
        costo_proyectado = costo * (1.0 + (factor_inflacion / 100.0))

        cant_vendida_45d = ventas_ritmo.get(r.id, 0.0)
        ritmo_diario = (cant_vendida_45d / 45.0) * multiplicador_escenario

        if stock <= 0:
            dias_autonomia = 0
            riesgo = 'CRITICO'
            repuestos_criticos_quiebre += 1
            capital_en_riesgo_quiebre += costo_proyectado * stock_min
        elif ritmo_diario > 0:
            dias_autonomia = int(stock // ritmo_diario)
            if dias_autonomia <= 15:
                riesgo = 'ALTO'
                repuestos_criticos_quiebre += 1
            elif dias_autonomia <= 30:
                riesgo = 'MEDIO'
            else:
                riesgo = 'BAJO'
        else:
            dias_autonomia = 999
            if stock > 0:
                riesgo = 'INMOVILIZADO'
                repuestos_inmovilizados += 1
            else:
                riesgo = 'SIN_MOVIMIENTO'

        if stock > 0:
            capital_inmovilizado_total += (stock * costo)

        demanda_proyectada_45d = int(ritmo_diario * 45) + (1 if (ritmo_diario * 45) % 1 > 0 else 0)
        necesidad_compra = max(0, (demanda_proyectada_45d + stock_min) - stock)

        nombre_desc = getattr(r, 'nombre', '') or getattr(r, 'descripcion', '') or f"Repuesto #{r.id}"
        codigo_rep = getattr(r, 'codigo', '') or getattr(r, 'sku', '') or f"ID-{r.id}"

        analisis_repuestos.append({
            'id': r.id,
            'codigo': codigo_rep,
            'nombre': nombre_desc,
            'stock': stock,
            'stock_minimo': stock_min,
            'ritmo_diario': round(ritmo_diario, 2),
            'dias_autonomia': dias_autonomia,
            'riesgo': riesgo,
            'costo_actual': costo,
            'costo_proyectado': costo_proyectado,
            'sugerencia_45d': necesidad_compra,
            'inversion_necesaria': round(necesidad_compra * costo_proyectado, 2)
        })

    analisis_repuestos.sort(key=lambda x: x['dias_autonomia'])

    # 5. Cobranzas y Cuentas Corrientes (filtradas por sucursal)
    deuda_total_clientes = 0.0
    try:
        query_cta = MovimientoCtaCte.query
        if sucursal_id and hasattr(MovimientoCtaCte, 'sucursal_id'):
            query_cta = query_cta.filter(MovimientoCtaCte.sucursal_id == sucursal_id)
        
        movs = query_cta.all()
        deuda_total_clientes = sum(float(m.monto or 0.0) for m in movs if getattr(m, 'tipo', '') == 'DEUDA')
    except Exception:
        deuda_total_clientes = 0.0

    cobranza_estimada_30d = deuda_total_clientes * 0.70

    # 6. Gráficos
    grafico_forecast_json = json.dumps({
        'labels': etiquetas_proyeccion,
        'historico': valores_proyectados,
        'prediccion': solo_predicciones
    })

    conteo_riesgos = {
        'Crítico (Quiebre / <15d)': sum(1 for x in analisis_repuestos if x['riesgo'] in ['CRITICO', 'ALTO']),
        'Alerta Media (15-30d)': sum(1 for x in analisis_repuestos if x['riesgo'] == 'MEDIO'),
        'Stock Saludable (>30d)': sum(1 for x in analisis_repuestos if x['riesgo'] == 'BAJO'),
        'Capital Inmovilizado': repuestos_inmovilizados
    }

    grafico_riesgos_json = json.dumps({
        'labels': list(conteo_riesgos.keys()),
        'data': list(conteo_riesgos.values()),
        'colors': ['#dc3545', '#ffc107', '#198754', '#6c757d']
    })

    # Carga de Sucursales para el desplegable
    sucursales = []
    try:
        if hasattr(Sucursal, 'nombre'):
            sucursales = Sucursal.query.order_by(Sucursal.nombre.asc()).all()
        elif hasattr(Sucursal, 'descripcion'):
            sucursales = Sucursal.query.order_by(Sucursal.descripcion.asc()).all()
        else:
            sucursales = Sucursal.query.all()
    except Exception:
        sucursales = []

    return render_template(
        'reportes/predictivo_ml.html',
        escenario=escenario,
        factor_inflacion=factor_inflacion,
        sucursales=sucursales,
        sucursal_id_sel=sucursal_id,
        total_proyectado_30d=total_proyectado_30d,
        total_proyectado_60d=total_proyectado_60d,
        total_proyectado_90d=total_proyectado_90d,
        capital_inmovilizado_total=capital_inmovilizado_total,
        repuestos_criticos_quiebre=repuestos_criticos_quiebre,
        repuestos_inmovilizados=repuestos_inmovilizados,
        deuda_total_clientes=deuda_total_clientes,
        cobranza_estimada_30d=cobranza_estimada_30d,
        repuestos_alerta=analisis_repuestos[:15],
        grafico_forecast_json=grafico_forecast_json,
        grafico_riesgos_json=grafico_riesgos_json
    )