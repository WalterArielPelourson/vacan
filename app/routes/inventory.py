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
@login_required
def index():
    # 1. Capturamos los filtros de la URL
    f_rubro = request.args.get('rubro')
    f_subrubro = request.args.get('subrubro')
    f_sucursal = request.args.get('sucursal_id', type=int)
    f_stock = request.args.get('stock_status') # 'disponible' o 'agotado'
    f_vehiculo = request.args.get('modelo_id', type=int)

    # 2. Construimos la consulta base
    query = Repuesto.query

    # 3. Aplicamos filtros si el usuario eligió alguno
    if f_rubro:
        query = query.filter_by(rubro=f_rubro)
    if f_subrubro:
        query = query.filter_by(subrubro=f_subrubro)
    if f_sucursal:
        query = query.filter_by(sucursal_id=f_sucursal)
        
    # --- NUEVO FILTRO DE STOCK ---
    if f_stock == 'disponible':
        query = query.filter(Repuesto.stock > 0)
    elif f_stock == 'agotado':
        query = query.filter(Repuesto.stock <= 0)
    # -----------------------------

    # --- FILTRO POR VEHÍCULO (RELACIÓN MUCHOS A MUCHOS) ---
    if f_vehiculo:
        query = query.join(Repuesto.autos_compatibles).filter(ModeloAuto.id == f_vehiculo)
        
        
    # Traemos los repuestos filtrados
    repuestos = query.order_by(Repuesto.id.desc()).all()

    # 4. Obtenemos datos únicos para llenar los selectores del HTML
    rubros_unicos = db.session.query(Repuesto.rubro).distinct().all()
    subrubros_unicos = db.session.query(Repuesto.subrubro).distinct().all()
    # Traemos las sucursales para el filtro
    sucursales = Sucursal.query.filter_by(activo=True).all()
    vehiculos = ModeloAuto.query.order_by(ModeloAuto.marca).all()
    
    # --- APLICACIÓN DEL PUNTO 3: Sincronización de nombres con el HTML ---
    # Cambiamos los nombres de las variables para que el HTML los reconozca
    return render_template('index.html', 
                           repuestos=repuestos,
                           rubros_list=[r[0] for r in rubros_unicos if r[0]],
                           subrubros_list=[s[0] for s in subrubros_unicos if s[0]],
                           sucursales_list=sucursales,
                           vehiculos_list=vehiculos,
                           busqueda=None)
    
    
    
@inventory_bp.route('/repuesto/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_repuesto():
    if current_user.rol not in ['admin', 'superadmin']:
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
            sucursal_id=request.form.get('sucursal_id'),    # ID de Sucursal
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
    modelos = ModeloAuto.query.order_by(ModeloAuto.marca).all()
    
    return render_template('nuevo_repuesto.html', 
                           sugerencia_sku=sugerencia, 
                           sucursales=sucursales, 
                           modelos=modelos)


from app.models import Repuesto, ModeloAuto, HistorialPrecio, Sucursal, Proveedor # Asegúrate de importar Proveedor

@inventory_bp.route('/repuesto/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_repuesto(id):
    # Solo admin o superadmin pueden editar
    if current_user.rol not in ['admin', 'superadmin']:
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
    productos = Repuesto.query.filter(Repuesto.stock > 0).all()
    clientes = Cliente.query.filter_by(activo=True).all()
    
    # --- NUEVO: Traemos las cajas de la sucursal actual + las virtuales ---
    cajas = Caja.query.filter(
        (Caja.sucursal_id == current_user.sucursal_id) | (Caja.tipo == 'VIRTUAL')
    ).all()
    
    return render_template('pos.html', productos=productos, clientes=clientes, cajas=cajas)


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
    
    try:
        # --- CASO A: PRESUPUESTO (No toca Stock ni Caja) ---
        if destino == 'PRESUPUESTO':
            nuevo_preso = Presupuesto(
                total=total_operacion,
                cliente_id=cliente_id,
                usuario_id=current_user.id,
                sucursal_id=current_user.sucursal_id,
                estado='PENDIENTE'
            )
            db.session.add(nuevo_preso)
            db.session.flush()

            for item in items:
                es_manual = not str(item['id']).isdigit()
                id_repuesto = None if es_manual else int(item['id'])
                
                detalle_p = DetallePresupuesto(
                    presupuesto_id=nuevo_preso.id,
                    repuesto_id=id_repuesto,
                    nombre_item=item.get('nombre', 'Sin nombre'),
                    cantidad=int(item['cantidad']),
                    precio_pactado=float(item['precio'])
                )
                db.session.add(detalle_p)
            
            db.session.commit()
            return jsonify({"status": "ok", "presupuesto_id": nuevo_preso.id, "tipo": "PRESUPUESTO"})

        # --- CASO B: VENTA REAL (Remito/Factura/Interno) ---
        else:
            metodo_pago = pago_info.get('medio', 'EFECTIVO')
            if destino == 'CTA_CTE':
                metodo_pago = 'CTA_CTE'

            estado_fiscal = 'FACTURADO' if destino == 'FACTURA' else 'PENDIENTE'
            if destino == 'INTERNO':
                estado_fiscal = 'NO_APLICA'

            # 1. Crear la Venta base
            nueva_venta = Venta(
                total=total_operacion,
                cliente_id=cliente_id,
                usuario_id=current_user.id,
                sucursal_id=current_user.sucursal_id,
                tipo_comprobante='REMITO',
                metodo_pago=metodo_pago,
                estado_arca=estado_fiscal
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
    
    # 1. Crear la Venta (Remito)
    nueva_venta = Venta(
        total=p.total, cliente_id=p.cliente_id, 
        usuario_id=current_user.id, sucursal_id=current_user.sucursal_id,
        tipo_comprobante='REMITO', metodo_pago='CTA_CTE', estado_arca='PENDIENTE'
    )
    db.session.add(nueva_venta)
    db.session.flush()

    # 2. Mover detalles y DESCONTAR STOCK (Recién ahora)
    for dp in p.detalles:
        detalle_v = DetalleVenta(venta_id=nueva_venta.id, repuesto_id=dp.repuesto_id, 
                                 cantidad=dp.cantidad, precio_unitario=dp.precio_pactado)
        dp.repuesto.stock -= dp.cantidad
        db.session.add(detalle_v)

    # 3. Impactar Cta Cte y marcar presupuesto como usado
    mov = MovimientoCtaCte(cliente_id=p.cliente_id, venta_id=nueva_venta.id, 
                           monto=p.total, tipo='DEUDA', descripcion=f"Remito #{nueva_venta.id} (ex Presup #{p.id})")
    p.estado = 'CONVERTIDO'
    
    db.session.add(mov)
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

    cliente_id = data.get('cliente_id')
    items = data.get('items') 
    pagos = data.get('pagos') 
    tipo_comp = data.get('tipo_comprobante', 'REMITO')
    
    # --- NUEVOS CAMPOS RECIBIDOS ---
    iva_p = float(data.get('iva_porcentaje', 21.0))
    plazo = int(data.get('plazo_pago', 0))
    recargo_p = float(data.get('recargo_porcentaje', 0))
    descuento_p = float(data.get('descuento_porcentaje', 0))

    # 1. Cálculo del Total con Ajustes e IVA
    # Sumamos los subtotales de los ítems (Precio unitario pactado * cantidad)
    subtotal_items = sum(float(item['precio']) * int(item['cantidad']) for item in items)
    
    # Aplicamos primero el Recargo sobre el neto de los productos
    neto_con_ajustes = subtotal_items * (1 + (recargo_p / 100))
    # Aplicamos el Descuento sobre el resultado anterior
    neto_con_ajustes = neto_con_ajustes * (1 - (descuento_p / 100))
    
    # --- AQUÍ SUMAMOS EL IVA AL TOTAL FINAL ---
    total_con_iva = neto_con_ajustes * (1 + (iva_p / 100))
    total_venta = round(total_con_iva, 2)
    
    try:
        # 2. Crear el objeto Venta con el Total Real (IVA incluido)
        nueva_v = Venta(
            total=total_venta,
            cliente_id=cliente_id,
            usuario_id=current_user.id,
            sucursal_id=current_user.sucursal_id,
            tipo_comprobante=tipo_comp,
            estado_arca='FACTURADO' if tipo_comp == 'FACTURA' else 'PENDIENTE',
            iva_porcentaje=iva_p, 
            plazo_pago=plazo      
        )
        db.session.add(nueva_v)
        db.session.flush() 

        # 3. Procesar los Ítems del Carrito
        for item in items:
            item_id = str(item['id'])
            es_man = item_id.startswith('MAN_')
            
            id_rep = None
            if not es_man:
                rep = Repuesto.query.get(int(item['id']))
                if rep:
                    if rep.stock < int(item['cantidad']):
                         raise Exception(f"Stock insuficiente para {rep.nombre}")
                    rep.stock -= int(item['cantidad'])
                    id_rep = rep.id

            db.session.add(DetalleVenta(
                venta_id=nueva_v.id, 
                repuesto_id=id_rep,
                nombre_item=item['nombre'].upper(),
                cantidad=int(item['cantidad']), 
                precio_unitario=float(item['precio']) 
            ))

        # 4. Procesar la Bolsa de Pagos
        total_abonado_real = 0
        for p in pagos:
            if p is None: continue
            
            monto_p = float(p.get('monto', 0))
            medio = p.get('medio')
            caja_id_manual = p.get('caja_id') # <--- EL ID QUE ELEGISTE EN EL POS

            if medio == 'CTA_CTE':
                # Lógica de Cuenta Corriente (No toca cajas)
                desc_cta = f"Venta {tipo_comp} #{nueva_v.id}"
                if plazo > 0:
                    fecha_venc = (get_argentina_time() + timedelta(days=plazo)).strftime('%d/%m/%Y')
                    desc_cta += f" - VENCE: {fecha_venc}"
                
                db.session.add(MovimientoCtaCte(
                    cliente_id=cliente_id, venta_id=nueva_v.id, monto=monto_p,
                    tipo='DEUDA', sucursal_id=current_user.sucursal_id, descripcion=desc_cta
                ))
            else:
                # DINERO REAL: Impacta en la caja seleccionada manualmente
                total_abonado_real += monto_p
                
                if caja_id_manual:
                    caja_destino = Caja.query.get(caja_id_manual) # <--- BUSCAMOS LA CAJA EXACTA
                    
                    if caja_destino:
                        # 1. Sumamos al saldo de esa caja específica (Física o Virtual)
                        caja_destino.saldo_actual += monto_p
                        
                        # 2. Registramos el movimiento en esa caja específica
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
                    # Si por algún error no llegó el ID, lanzamos error para no perder rastro del dinero
                    raise Exception(f"No se seleccionó una caja de destino para el pago con {medio}")

                # Lógica de Cheque (Si corresponde)
                if medio == 'CHEQUE':
                    d = p.get('cheque_data')
                    if d:
                        db.session.add(Cheque(
                            banco=d.get('banco', 'S/D').upper(), 
                            numero=d.get('numero', '0'), 
                            emisor=d.get('emisor', 'S/D').upper(),
                            monto=monto_p,
                            fecha_vencimiento=datetime.strptime(d.get('vencimiento'), '%Y-%m-%d').date() if d.get('vencimiento') else get_argentina_time().date(),
                            tipo='FISICO', cliente_id=cliente_id, venta_id=nueva_v.id, estado='EN_CARTERA'
                        ))
        # 5. Finalizar Venta
        # La venta se marca como pagada SOLO SI el dinero real cubre el total de la operación.
        nueva_v.total_pagado = total_abonado_real
        nueva_v.esta_pagada = (total_abonado_real >= (total_venta - 0.05)) 
        
        db.session.commit()
        return jsonify({"status": "ok", "venta_id": nueva_v.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500