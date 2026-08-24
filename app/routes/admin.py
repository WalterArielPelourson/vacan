import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date 
# Busca esta línea al principio del archivo y agrégale Caja y MovimientoFinanciero
from app.models import db, Empresa, Sucursal, Usuario, Venta, Cliente, Proveedor, MovimientoCtaCte, Caja, MovimientoFinanciero, Cheque,  CategoriaMovimiento, CierreCaja, Compra, DetalleCompra, MovimientoCtaCteProveedor, Repuesto, HistorialPrecio, get_argentina_time, Traspaso, DetalleTraspaso, DetalleVenta
from werkzeug.security import generate_password_hash
from sqlalchemy import func, or_, and_, extract, text
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from xhtml2pdf import pisa
from flask import make_response
from sqlalchemy.orm import joinedload
from datetime import timedelta

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Decorador para restringir el acceso únicamente a Superadmin
def superadmin_required(f):
    def wrap(*args, **kwargs):
        if current_user.rol != 'superadmin':
            flash("Acceso denegado: Se requieren permisos de Superadmin", "danger")
            return redirect(url_for('inventory.index'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@admin_bp.route('/dashboard')
@login_required
@superadmin_required
def dashboard():
    empresas = Empresa.query.all()
    sucursales = Sucursal.query.all()
    usuarios = Usuario.query.all()
    return render_template('admin/dashboard.html', empresas=empresas, sucursales=sucursales, usuarios=usuarios)

# --- ABM SUCURSALES ---

@admin_bp.route('/sucursal/nueva', methods=['POST'])
@login_required
@superadmin_required
def nueva_sucursal():
    # Creamos la sucursal con todos los campos (incluyendo los opcionales)
    nueva = Sucursal(
        nombre=request.form.get('nombre'),
        cuit=request.form.get('cuit'),
        direccion=request.form.get('direccion'),
        localidad=request.form.get('localidad'),
        provincia=request.form.get('provincia'),
        celular=request.form.get('celular'),
        celular_alternativo=request.form.get('celular_alternativo'),
        empresa_id=1, # Asignada a Vacan Radiadores (ID 1)
        activo=True
    )
    db.session.add(nueva)
    db.session.commit()
    flash(f"Sucursal {nueva.nombre} creada con éxito", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/sucursal/editar/<int:id>', methods=['POST'])
@login_required
@superadmin_required
def editar_sucursal(id):
    suc = Sucursal.query.get_or_404(id)
    # Actualizamos todos los datos desde el formulario
    suc.nombre = request.form.get('nombre')
    suc.cuit = request.form.get('cuit')
    suc.direccion = request.form.get('direccion')
    suc.localidad = request.form.get('localidad')
    suc.provincia = request.form.get('provincia')
    suc.celular = request.form.get('celular')
    suc.celular_alternativo = request.form.get('celular_alternativo')
    
    db.session.commit()
    flash(f"Sucursal {suc.nombre} actualizada correctamente", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/sucursal/estado/<int:id>')
@login_required
@superadmin_required
def toggle_sucursal(id):
    suc = Sucursal.query.get_or_404(id)
    suc.activo = not suc.activo  # Alterna entre True y False
    db.session.commit()
    estado = "activada" if suc.activo else "desactivada"
    flash(f"Sucursal {suc.nombre} ha sido {estado}", "info")
    return redirect(url_for('admin.dashboard'))

# --- ABM USUARIOS ---

@admin_bp.route('/usuario/nuevo', methods=['POST'])
@login_required
@superadmin_required
def nuevo_usuario():
    username = request.form.get('username')
    password = request.form.get('password')
    rol = request.form.get('rol')
    sucursal_id = request.form.get('sucursal_id')
    
    # Verificamos si el nombre de usuario ya está tomado
    if Usuario.query.filter_by(username=username).first():
        flash("El nombre de usuario ya existe en el sistema", "danger")
        return redirect(url_for('admin.dashboard'))

    nuevo = Usuario(
        username=username, 
        password_hash=password, # En desarrollo comparamos directo
        rol=rol, 
        sucursal_id=sucursal_id if sucursal_id else None,
        activo=True
    )
    db.session.add(nuevo)
    db.session.commit()
    flash(f"Usuario {username} creado con éxito", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/usuario/editar/<int:id>', methods=['POST'])
@login_required
@superadmin_required
def editar_usuario(id):
    user = Usuario.query.get_or_404(id)
    user.rol = request.form.get('rol')
    user.sucursal_id = request.form.get('sucursal_id') or None
    
    # Si se ingresó una nueva contraseña, se actualiza, si no, se mantiene la anterior
    nueva_pass = request.form.get('password')
    if nueva_pass:
        user.password_hash = nueva_pass
        
    db.session.commit()
    flash(f"Datos de {user.username} actualizados correctamente", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/usuario/estado/<int:id>')
@login_required
@superadmin_required
def toggle_usuario(id):
    user = Usuario.query.get_or_404(id)
    # Seguridad: Un superadmin no puede desactivarse a sí mismo
    if user.id == current_user.id:
        flash("No puedes desactivar tu propia cuenta de Superadmin", "danger")
    else:
        user.activo = not user.activo
        db.session.commit()
        estado = "activado" if user.activo else "desactivado"
        flash(f"Usuario {user.username} ha sido {estado}", "info")
    return redirect(url_for('admin.dashboard'))

# --- SECCIÓN DE REPORTES ---

@admin_bp.route('/reportes')
@login_required
@superadmin_required
def reportes():
    sucursal_id = request.args.get('sucursal_id', type=int)
    sucursales = Sucursal.query.all()
    
    query_ventas = Venta.query

    # Si se selecciona una sucursal, filtramos los reportes
    if sucursal_id:
        query_ventas = query_ventas.filter_by(sucursal_id=sucursal_id)
        sucursal_actual = Sucursal.query.get(sucursal_id)
    else:
        sucursal_actual = None

    # Ordenamos por fecha descendente (más reciente primero)
    ventas = query_ventas.order_by(Venta.id.desc()).all()
    
    # Cálculos globales para el Dashboard de reportes
    total_recaudado = sum(v.total for v in ventas)
    cantidad_ventas = len(ventas)

    return render_template(
        'admin/reportes.html', 
        ventas=ventas, 
        total=total_recaudado, 
        cantidad=cantidad_ventas,
        sucursales=sucursales,
        sucursal_actual=sucursal_actual
    )
    
    
    
from app.models import Cliente, Proveedor

@admin_bp.route('/contactos')
@login_required
def lista_contactos():
    clientes = Cliente.query.all()
    proveedores = Proveedor.query.all()
    # Lista de condiciones de IVA típicas en Argentina para los selectores
    condiciones_iva = [
        "Responsable Inscripto", 
        "Monotributista", 
        "Exento", 
        "Consumidor Final", 
        "No Responsable"
    ]
    return render_template('admin/contactos.html', clientes=clientes, proveedores=proveedores, condiciones=condiciones_iva)



#CLIENTE PROVEEDOR
@admin_bp.route('/cliente/nuevo', methods=['POST'])
@login_required
def nuevo_cliente():
    # --- PUNTO 2: DETECTAR EL ORIGEN DEL PEDIDO ---
    # Esto permite que si venimos del POS, el sistema nos regrese allí
    cuit = request.form.get('cuit').strip()
    next_page = request.args.get('next') 
    # Verificar si el CUIT ya existe
    if cuit and cuit != "00-00000000-0": # No verificamos si es consumidor final genérico
        existente = Cliente.query.filter_by(cuit=cuit).first()
        if existente:
            flash(f"El CUIT/DNI {cuit} ya está registrado a nombre de {existente.razon_social}.", "warning")
            return redirect(url_for('inventory.pos' if next_page == 'pos' else 'admin.lista_contactos'))
    

    nuevo = Cliente(
        razon_social=request.form.get('razon_social').upper(),
        cuit=request.form.get('cuit'),
        condicion_iva=request.form.get('condicion_iva'),
        direccion=request.form.get('direccion'),
        localidad=request.form.get('localidad'),
        provincia=request.form.get('provincia'),
        telefono=request.form.get('telefono'),
        email=request.form.get('email'),
        iibb=request.form.get('iibb'),
        activo=True # Aseguramos que el nuevo cliente inicie como activo
    )
    
    db.session.add(nuevo)
    db.session.commit()
    
    flash(f"Cliente {nuevo.razon_social} registrado con éxito", "success")

    # --- LÓGICA DE RETORNO INTELIGENTE ---
    if next_page == 'pos':
        return redirect(url_for('inventory.pos'))
    
    return redirect(url_for('admin.lista_contactos'))




@admin_bp.route('/proveedor/nuevo', methods=['POST'])
@login_required
def nuevo_proveedor():
    cuit = request.form.get('cuit').strip()
    
    # --- VERIFICACIÓN DE DUPLICADOS ---
    # Buscamos si ya existe un proveedor con ese CUIT
    existente = Proveedor.query.filter_by(cuit=cuit).first()
    
    if existente:
        flash(f"Error: El CUIT {cuit} ya pertenece al proveedor '{existente.razon_social}'.", "danger")
        return redirect(url_for('admin.lista_contactos'))
    # ----------------------------------

    try:
        nuevo = Proveedor(
            razon_social=request.form.get('razon_social').upper(),
            cuit=cuit,
            condicion_iva=request.form.get('condicion_iva'),
            direccion=request.form.get('direccion'),
            telefono=request.form.get('telefono'),
            iibb=request.form.get('iibb'),
            activo=True
        )
        db.session.add(nuevo)
        db.session.commit()
        flash(f"Proveedor {nuevo.razon_social} registrado con éxito", "success")
    except Exception as e:
        db.session.rollback() # Limpia la sesión si algo falla
        flash(f"Error al guardar: {str(e)}", "danger")
        
    return redirect(url_for('admin.lista_contactos'))


# --- EDICIÓN E INACTIVACIÓN DE CLIENTES ---

@admin_bp.route('/cliente/editar/<int:id>', methods=['POST'])
@login_required
def editar_cliente(id):
    c = Cliente.query.get_or_404(id)
    c.razon_social = request.form.get('razon_social').upper()
    c.cuit = request.form.get('cuit')
    c.condicion_iva = request.form.get('condicion_iva')
    c.direccion = request.form.get('direccion')
    c.localidad = request.form.get('localidad')
    c.provincia = request.form.get('provincia')
    c.telefono = request.form.get('telefono')
    c.email = request.form.get('email')
    c.iibb = request.form.get('iibb')
    db.session.commit()
    flash(f"Cliente {c.razon_social} actualizado.", "success")
    return redirect(url_for('admin.lista_contactos'))

@admin_bp.route('/cliente/estado/<int:id>')
@login_required
def toggle_cliente(id):
    c = Cliente.query.get_or_404(id)
    c.activo = not c.activo
    db.session.commit()
    estado = "activado" if c.activo else "inactivado"
    flash(f"Cliente {c.razon_social} {estado}.", "info")
    return redirect(url_for('admin.lista_contactos'))

# --- EDICIÓN E INACTIVACIÓN DE PROVEEDORES ---

@admin_bp.route('/proveedor/editar/<int:id>', methods=['POST'])
@login_required
def editar_proveedor(id):
    p = Proveedor.query.get_or_404(id)
    p.razon_social = request.form.get('razon_social').upper()
    p.cuit = request.form.get('cuit')
    p.condicion_iva = request.form.get('condicion_iva')
    p.direccion = request.form.get('direccion')
    p.telefono = request.form.get('telefono')
    p.iibb = request.form.get('iibb')
    db.session.commit()
    flash(f"Proveedor {p.razon_social} actualizado.", "success")
    return redirect(url_for('admin.lista_contactos'))

@admin_bp.route('/proveedor/estado/<int:id>')
@login_required
def toggle_proveedor(id):
    p = Proveedor.query.get_or_404(id)
    p.activo = not p.activo
    db.session.commit()
    estado = "activado" if p.activo else "inactivado"
    flash(f"Proveedor {p.razon_social} {estado}.", "info")
    return redirect(url_for('admin.lista_contactos'))


@admin_bp.route('/proveedores/saldos')
@login_required
def lista_saldos_proveedores():
    # 1. Obtener todos los proveedores
    proveedores = Proveedor.query.all()
    resumen = []
    deuda_total_general = 0 # <--- NUEVA VARIABLE PARA EL TOTAL

    for p in proveedores:
        # Calculamos el saldo individual (Facturas - Pagos)
        saldo = db.session.query(func.sum(MovimientoCtaCteProveedor.monto)).filter_by(proveedor_id=p.id).scalar() or 0
        resumen.append({
            'id': p.id, 
            'razon_social': p.razon_social, 
            'cuit': p.cuit, 
            'saldo': saldo
        })
        # Sumamos al total general de la empresa
        deuda_total_general += saldo

    # Variables para el Modal de Pago
    todas_las_cajas = Caja.query.all()
    cheques_en_cartera = Cheque.query.filter_by(estado='EN_CARTERA').all()

    # Enviamos 'total_general' al HTML
    return render_template('admin/proveedores_saldos.html', 
                           proveedores=resumen, 
                           total_general=deuda_total_general, # <--- ENVIADO
                           cajas=todas_las_cajas, 
                           cheques_en_cartera=cheques_en_cartera)
    
    
@admin_bp.route('/proveedores/pago/<int:id>', methods=['POST'])
@login_required
def registrar_pago_proveedor(id):
    prov = Proveedor.query.get_or_404(id)
    
    # Capturamos los datos del modal
    monto = float(request.form.get('monto'))
    caja_id = request.form.get('caja_id') # <--- ID de la caja seleccionada (Mostrador, Grande o Virtual)
    medio = request.form.get('medio_pago')
    referencia = request.form.get('referencia') or "S/R"

    # 1. Registro en la Cta Cte del Proveedor (Baja la deuda histórica)
    nuevo_pago_prov = MovimientoCtaCteProveedor(
        proveedor_id=id,
        monto=-monto, 
        descripcion=f"Pago con {medio} - Ref: {referencia}"
    )
    db.session.add(nuevo_pago_prov)

    # 2. PROCESAMIENTO SEGÚN EL MEDIO DE PAGO
    if medio == 'CHEQUE_TERCEROS':
        # --- CASO A: ENDOSO DE CHEQUE ---
        cheque_id = request.form.get('cheque_id')
        ch = Cheque.query.get(cheque_id)
        
        if ch:
            ch.estado = 'ENTREGADO'
            ch.proveedor_id = id 
            
            # Buscamos la caja de donde sale el "papel" (Elegida en el modal)
            caja_donde_estaba = Caja.query.get(caja_id)
            if caja_donde_estaba:
                caja_donde_estaba.saldo_actual -= ch.monto
                mov_f_ch = MovimientoFinanciero(
                    caja_id=caja_donde_estaba.id,
                    monto=ch.monto,
                    tipo='EGRESO',
                    motivo=f"Endoso Cheque {ch.banco} N°{ch.numero} a {prov.razon_social}",
                    metodo_detalle='CHEQUE_TERCEROS',
                    usuario_id=current_user.id
                )
                db.session.add(mov_f_ch)
        else:
            flash("Error: El cheque seleccionado no es válido.", "danger")
            return redirect(url_for('admin.detalle_cta_cte_proveedor', id=id))

    else:
        # --- CASO B: EFECTIVO (MOSTRADOR O GRANDE) O TRANSFERENCIA ---
        # El sistema usa el caja_id que vos elegiste (Caja Grande, Banco, etc.)
        caja_elegida = Caja.query.get(caja_id)
        
        if caja_elegida:
            # Descuento real del saldo de ESA caja específica
            caja_elegida.saldo_actual -= monto
            
            # Registro en el historial de ESA caja
            mov_f = MovimientoFinanciero(
                caja_id=caja_elegida.id,
                monto=monto,
                tipo='EGRESO',
                motivo=f"Pago a Proveedor: {prov.razon_social}",
                metodo_detalle=medio,
                usuario_id=current_user.id
            )
            db.session.add(mov_f)
        else:
            flash("Error: Debe seleccionar una cuenta de origen válida.", "danger")
            return redirect(url_for('admin.detalle_cta_cte_proveedor', id=id))

    db.session.commit()
    flash(f"Operación exitosa. Se actualizaron los saldos de {caja_elegida.nombre if medio != 'CHEQUE_TERCEROS' else 'Caja'}.", "success")
    return redirect(url_for('admin.detalle_cta_cte_proveedor', id=id))

   

@admin_bp.route('/proveedores/detalle/<int:id>')
@login_required
def detalle_cta_cte_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    # Obtenemos los movimientos (Compras y Pagos)
    movimientos = MovimientoCtaCteProveedor.query.filter_by(proveedor_id=id).order_by(MovimientoCtaCteProveedor.fecha.desc()).all()
    
    # Calculamos el saldo actual
    saldo_actual = sum(m.monto for m in movimientos)
    
    # Variables para el Modal de Pago (Igual que en Clientes)
    cajas = Caja.query.all()
    cheques_en_cartera = Cheque.query.filter_by(estado='EN_CARTERA').all()
    
    return render_template('admin/proveedores_detalle.html', 
                           proveedor=proveedor, 
                           movimientos=movimientos, 
                           saldo=saldo_actual,
                           cajas=cajas,
                           cheques_en_cartera=cheques_en_cartera)

@admin_bp.route('/cta-cte')
@login_required
def lista_cta_cte():
    clientes = Cliente.query.all()
    saldos = []
    deuda_total_global = 0 # <--- NUEVA VARIABLE PARA LA SUMATORIA

    for c in clientes:
        # Sumamos movimientos (Deuda - Pagos)
        saldo_individual = db.session.query(func.sum(MovimientoCtaCte.monto)).filter_by(cliente_id=c.id).scalar() or 0
        
        saldos.append({
            'id': c.id,
            'razon_social': c.razon_social,
            'cuit': c.cuit,
            'saldo': saldo_individual
        })
        
        # Solo sumamos al total global si es deuda (saldo positivo)
        if saldo_individual > 0:
            deuda_total_global += saldo_individual

    return render_template('admin/cta_cte_lista.html', 
                           saldos=saldos, 
                           total_global=deuda_total_global) # <--- ENVIADO AL HTML
    
    

#@admin_bp.route('/cta-cte/<int:cliente_id>')
#@login_required
#def detalle_cta_cte(cliente_id):
#    cliente = Cliente.query.get_or_404(cliente_id)
#    movimientos = MovimientoCtaCte.query.filter_by(cliente_id=cliente_id).order_by(MovimientoCtaCte.fecha.desc()).all()
#    saldo_actual = sum(m.monto for m in movimientos)
#    cajas = Caja.query.all() 
#    
#    # --- NUEVO: Enviamos la fecha de hoy ---
#    hoy = get_argentina_time().date() 
#    
#    return render_template('admin/cta_cte_detalle.html', 
#                           cliente=cliente, 
#                           movimientos=movimientos, 
#                           saldo=saldo_actual,
#                           cajas=cajas,
#                           hoy=hoy) # <--- Variable clave
    


@admin_bp.route('/cta-cte/<int:cliente_id>')
@login_required
def detalle_cta_cte(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # --- CAMBIO AQUÍ: Forzamos la carga de la venta y sus detalles ---
    movimientos = MovimientoCtaCte.query.options(
        joinedload(MovimientoCtaCte.venta).joinedload(Venta.detalles)
    ).filter_by(cliente_id=cliente_id).order_by(MovimientoCtaCte.fecha.desc()).all()
    # -----------------------------------------------------------------
    
    saldo_actual = sum(m.monto for m in movimientos)
    cajas = Caja.query.all()
    hoy = get_argentina_time().date()
    
    return render_template('admin/cta_cte_detalle.html', 
                           cliente=cliente, movimientos=movimientos, 
                           saldo=saldo_actual, cajas=cajas, hoy=hoy)

@admin_bp.route('/proveedores/pago-compuesto/<int:id>', methods=['POST'])
@login_required
def pago_compuesto_proveedor(id):
    prov = Proveedor.query.get_or_404(id)
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No se recibieron datos"}), 400

    items_pago = data.get('pagos', [])
    conciliaciones = data.get('conciliaciones', [])
    
    # Calculamos el total de la bolsa de pagos
    total_abonado = sum(float(item['monto']) for item in items_pago)

    try:
        # 1. CREAMOS EL MOVIMIENTO PADRE (En Cta Cte Proveedor)
        nuevo_mov_prov = MovimientoCtaCteProveedor(
            proveedor_id=id,
            monto=-total_abonado, 
            descripcion=f"Pago Compuesto ({len(items_pago)} medios)",
            referencia=f"OP-{int(datetime.now().timestamp())}"
        )
        db.session.add(nuevo_mov_prov)
        db.session.flush() # Obtenemos el ID para los hijos

        # 2. PROCESAMOS LOS MEDIOS DE PAGO (Hijos)
        for item in items_pago:
            monto = float(item['monto'])
            medio = item['medio']
            caja_id = item.get('caja_id')

            # Descontamos de Caja/Banco (Si no es cheque, o para registrar la salida del valor)
            caja = Caja.query.get(caja_id)
            if caja:
                caja.saldo_actual -= monto
                mov_f = MovimientoFinanciero(
                    caja_id=caja.id, 
                    monto=monto, 
                    tipo='EGRESO',
                    motivo=f"Pago a Prov: {prov.razon_social}",
                    metodo_detalle=medio, 
                    pago_maestro=nuevo_mov_prov, # <--- VÍNCULO CORREGIDO (v3.2)
                    usuario_id=current_user.id
                )
                db.session.add(mov_f)
            
            # Si es cheque de terceros, lo vinculamos
            if medio == 'CHEQUE_TERCEROS':
                ch = Cheque.query.get(item['cheque_id'])
                if ch:
                    ch.estado = 'ENTREGADO'
                    ch.proveedor_id = id
                    ch.pago_maestro = nuevo_mov_prov # <--- VÍNCULO CORREGIDO (v3.2)

        # 3. LÓGICA DE CONCILIACIÓN (Aplicar a facturas específicas)
        if conciliaciones:
            for conc in conciliaciones:
                compra_obj = Compra.query.get(conc['compra_id'])
                monto_imputar = float(conc['monto'])
                if compra_obj:
                    compra_obj.total_pagado += monto_imputar
                    # Si el saldo llega a 0, marcamos como pagada
                    if (compra_obj.total - compra_obj.total_pagado) <= 0.01:
                        compra_obj.esta_pagada = True

        db.session.commit()
        return jsonify({"status": "ok", "movimiento_id": nuevo_mov_prov.id})

    except Exception as e:
        db.session.rollback()
        print(f"Error en Pago Proveedor: {str(e)}") # Esto saldrá en tu consola
        return jsonify({"status": "error", "message": str(e)}), 500    
    

@admin_bp.route('/cta-cte/pago/<int:cliente_id>', methods=['POST'])
@login_required
def registrar_pago(cliente_id):
    # --- CAPTURA DE DATOS DEL FORMULARIO ---
    monto = float(request.form.get('monto'))
    caja_id = request.form.get('caja_id') # <--- NUEVO: Captura la caja elegida manualmente
    medio = request.form.get('medio_pago') # 'EFECTIVO', 'TRANSFERENCIA', 'CHEQUE'
    descripcion = request.form.get('descripcion') or f"Cobranza en {medio}"
    
    # 1. Registrar el movimiento en la Cuenta Corriente del Cliente (Resta deuda)
    nuevo_pago = MovimientoCtaCte(
        cliente_id=cliente_id,
        monto=-monto, # Valor negativo para restar del saldo del cliente
        tipo='PAGO',
        descripcion=descripcion
    )
    db.session.add(nuevo_pago)

    # 2. Registrar la entrada de dinero en la Caja SELECCIONADA manualmente
    caja_destino = Caja.query.get(caja_id)
    
    if caja_destino:
        # Buscamos el nombre del cliente para un motivo más descriptivo
        cliente = Cliente.query.get(cliente_id)
        nombre_cliente = cliente.razon_social if cliente else f"ID #{cliente_id}"

        mov_fina = MovimientoFinanciero(
            caja_id=caja_destino.id,
            monto=monto,
            tipo='INGRESO',
            motivo=f"Cobranza Cliente: {nombre_cliente}",
            metodo_detalle=medio,
            usuario_id=current_user.id
        )
        
        # Actualizamos el saldo de la caja o cuenta virtual elegida
        caja_destino.saldo_actual += monto
        db.session.add(mov_fina)
    else:
        flash("Error: No se seleccionó una caja de destino válida.", "danger")
        return redirect(url_for('admin.detalle_cta_cte', cliente_id=cliente_id))

    # 3. SI ES UN CHEQUE: Creamos el registro en la cartera (Mantenido sin omisiones)
    if medio == 'CHEQUE':
        vencimiento_str = request.form.get('ch_vencimiento')
        nuevo_cheque = Cheque(
            banco=request.form.get('ch_banco').upper(),
            numero=request.form.get('ch_numero'),
            emisor=request.form.get('ch_emisor').upper() or "El Cliente",
            monto=monto,
            fecha_vencimiento=datetime.strptime(vencimiento_str, '%Y-%m-%d').date(),
            tipo=request.form.get('ch_tipo'),
            cliente_id=cliente_id,
            estado='EN_CARTERA'
        )
        db.session.add(nuevo_cheque)

    db.session.commit()
    flash(f"Cobranza de ${monto} registrada con éxito en {caja_destino.nombre}.", "success")
    return redirect(url_for('admin.detalle_cta_cte', cliente_id=cliente_id))


@admin_bp.route('/cta-cte/pago-compuesto/<int:id>', methods=['POST'])
@login_required
def pago_compuesto_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    data = request.get_json()
    items_cobro = data.get('pagos') # La plata que entra (efectivo, cheques, etc)
    
    # --- PUNTO 2: LÓGICA DE PAGOS PARCIALES (CONCILIACIÓN) ---
    # Recibimos una lista de: {"venta_id": 5, "monto_aplicado": 1500.50}
    conciliaciones = data.get('conciliaciones', []) 
    
    total_cobrado = 0

    try:
        # 1. Procesamos cada medio de pago que entró a la bolsa
        for p in items_cobro:
            monto_item = float(p['monto'])
            total_cobrado += monto_item
            caja_id = p.get('caja_id')
            medio = p['medio']

            # Ingreso a Caja/Banco
            caja = Caja.query.get(caja_id)
            if caja:
                caja.saldo_actual += monto_item
                mov_f = MovimientoFinanciero(
                    caja_id=caja.id, monto=monto_item, tipo='INGRESO',
                    motivo=f"Cobranza Cliente: {cliente.razon_social} ({medio})",
                    metodo_detalle=medio, usuario_id=current_user.id
                )
                db.session.add(mov_f)

            # Si es un Cheque, lo cargamos a la cartera
            if medio == 'CHEQUE':
                datos_ch = p.get('cheque_data')
                nuevo_ch = Cheque(
                    banco=datos_ch['banco'].upper(),
                    numero=datos_ch['numero'],
                    emisor=datos_ch['emisor'].upper(),
                    monto=monto_item,
                    fecha_vencimiento=datetime.strptime(datos_ch['vencimiento'], '%Y-%m-%d').date(),
                    tipo=datos_ch['tipo'],
                    cliente_id=id,
                    estado='EN_CARTERA'
                )
                db.session.add(nuevo_ch)

        # --- 2. APLICAR PAGOS PARCIALES A COMPROBANTES ---
        if conciliaciones:
            for conc in conciliaciones:
                venta_obj = Venta.query.get(conc['venta_id'])
                monto_a_imputar = float(conc['monto_aplicado'])
                
                if venta_obj:
                    # Sumamos el monto al total ya pagado de esa factura/remito
                    # Si antes era 0 y paga 500, total_pagado ahora es 500
                    venta_obj.total_pagado += monto_a_imputar
                    
                    # Si el saldo llega a 0 (o menos por redondeo), marcamos como pagada
                    if (venta_obj.total - venta_obj.total_pagado) <= 0:
                        venta_obj.esta_pagada = True
        # --------------------------------------------------

        # 3. Registrar el movimiento de PAGO en la Cta Cte del Cliente
        desc_pago = f"Cobranza Compuesta ({len(items_cobro)} medios)"
        if conciliaciones:
            desc_pago += f" - Aplicado parcial a {len(conciliaciones)} remitos"

        mov_c = MovimientoCtaCte(
            cliente_id=id,
            monto=-total_cobrado, # Valor negativo resta la deuda general
            tipo='PAGO',
            descripcion=desc_pago
        )
        db.session.add(mov_c)
        
        db.session.commit()
        return jsonify({"status": "ok"})

    except Exception as e:
        db.session.rollback()
        print(f"Error en cobranza parcial: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500   


@admin_bp.route('/reportes/morosidad')
@login_required
def reporte_morosidad():
    # 1. Parámetros de filtro y fecha actual
    filtro = request.args.get('filtro', 'vencidas') # 'vencidas' o 'proximas'
    hoy = get_argentina_time().date()
    
    # 2. Buscamos todas las ventas que NO estén totalmente pagadas
    # Filtramos por saldo pendiente (total - total_pagado > 0)
    ventas_pendientes = Venta.query.filter(Venta.total > Venta.total_pagado).all()
    
    reporte = []
    total_deuda_filtro = 0

    for v in ventas_pendientes:
        dias_pasados = (hoy - v.fecha.date()).days
        saldo = round(v.total - v.total_pagado, 2)
        
        # Categorización
        es_vencida = dias_pasados > 30
        
        # Aplicamos el filtro de la vista
        if (filtro == 'vencidas' and es_vencida) or (filtro == 'proximas' and not es_vencida):
            reporte.append({
                'venta': v,
                'cliente': v.cliente,
                'dias_pasados': dias_pasados,
                'dias_excedidos': dias_pasados - 30 if es_vencida else 0,
                'dias_restantes': 30 - dias_pasados if not es_vencida else 0,
                'saldo': saldo
            })
            total_deuda_filtro += saldo

    # 3. Ordenamos por Nombre de Cliente y luego por Días de forma descendente
    reporte.sort(key=lambda x: (x['cliente'].razon_social, -x['dias_pasados']))

    return render_template('admin/reporte_morosidad.html', 
                           reporte=reporte, 
                           filtro=filtro, 
                           total=total_deuda_filtro,
                           hoy=hoy)    

@admin_bp.route('/cta-cte/cobrar/<int:cliente_id>', methods=['POST'])
@login_required
def cobrar_cta_cte_avanzado(cliente_id):
    monto = float(request.form.get('monto'))
    medio = request.form.get('medio_pago') # 'EFECTIVO', 'TRANSFERENCIA', 'CHEQUE'
    
    # 1. Creamos el movimiento en la cuenta corriente del cliente (Resta deuda)
    nuevo_mov_cliente = MovimientoCtaCte(
        cliente_id=cliente_id,
        monto=-monto, # Negativo porque descuenta deuda
        tipo='PAGO',
        descripcion=f"Cobranza en {medio}"
    )
    db.session.add(nuevo_mov_cliente)

    # 2. Registramos la entrada de dinero en Tesorería
    if medio == 'EFECTIVO':
        caja = Caja.query.filter_by(sucursal_id=current_user.sucursal_id, tipo='FISICA').first()
    else:
        caja = Caja.query.filter_by(tipo='VIRTUAL').first()

    if caja:
        mov_financiero = MovimientoFinanciero(
            caja_id=caja.id,
            monto=monto,
            tipo='INGRESO',
            motivo=f"Cobranza Cta. Cte. - Cliente ID: {cliente_id}",
            metodo_detalle=medio,
            usuario_id=current_user.id
        )
        caja.saldo_actual += monto
        db.session.add(mov_financiero)

    # 3. Si es Cheque, lo guardamos en la cartera
    if medio == 'CHEQUE':
        nuevo_cheque = Cheque(
            banco=request.form.get('banco'),
            numero=request.form.get('nro_cheque'),
            monto=monto,
            fecha_vencimiento=datetime.strptime(request.form.get('vencimiento'), '%Y-%m-%d'),
            tipo=request.form.get('tipo_cheque'),
            cliente_id=cliente_id
        )
        db.session.add(nuevo_cheque)

    db.session.commit()
    flash("Cobranza registrada y fondos acreditados en Tesorería", "success")
    return redirect(url_for('admin.detalle_cta_cte', cliente_id=cliente_id))


from datetime import datetime

@admin_bp.route('/cta-cte/facturar-remito/<int:venta_id>')
@login_required
def facturar_remito_cta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    venta.estado_arca = 'FACTURADO'
    db.session.commit()
    flash(f"Remito #{venta_id} marcado como Facturado", "success")
    # Volvemos al detalle de la cuenta corriente del cliente
    return redirect(url_for('admin.detalle_cta_cte', cliente_id=venta.cliente_id))

@admin_bp.route('/cta-cte/editar-fecha/<int:venta_id>', methods=['POST'])
@login_required
def editar_fecha_remito_cta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    nueva_fecha_str = request.form.get('nueva_fecha')
    
    # Convertimos la fecha del formulario (HTML datetime-local)
    nueva_fecha = datetime.strptime(nueva_fecha_str, '%Y-%m-%dT%H:%M')
    venta.fecha = nueva_fecha
    
    # También actualizamos la fecha del movimiento en la Cta Cte para que coincidan
    movimiento = MovimientoCtaCte.query.filter_by(venta_id=venta_id).first()
    if movimiento:
        movimiento.fecha = nueva_fecha
        
    db.session.commit()
    flash(f"Fecha del Remito #{venta_id} actualizada", "info")
    return redirect(url_for('admin.detalle_cta_cte', cliente_id=venta.cliente_id))

import requests
from bs4 import BeautifulSoup

@admin_bp.route('/api/arca/consultar/<cuit>')
@login_required
def consultar_cuit_arca(cuit):
    cuit = cuit.replace("-", "").strip()
    
    if len(cuit) != 11:
        return jsonify({"status": "error", "message": "CUIT inválido."}), 400

    try:
        # Usamos un servicio de consulta de CUITs más abierto (API de Jidoka o similares)
        # Este servicio es gratuito y muy usado en Argentina para pruebas
        url = f"https://afip.jidoka.com.ar/api/v1/cuits/{cuit}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extraemos los datos según la estructura de esta API
            razon_social = data.get('nombre', 'Nombre no encontrado')
            
            # Detectamos la condición de IVA
            # La API suele devolver un campo 'tipo' o 'estado'
            tipo_persona = data.get('tipo', '').upper()
            condicion = "Consumidor Final"
            
            if "INSCRIPTO" in tipo_persona:
                condicion = "Responsable Inscripto"
            elif "MONOTRIBUTO" in tipo_persona:
                condicion = "Monotributista"
            elif "EXENTO" in tipo_persona:
                condicion = "Exento"

            return jsonify({
                "status": "ok",
                "datos": {
                    "razon_social": razon_social,
                    "condicion_iva": condicion,
                    "cuit": cuit
                }
            })
        
        elif response.status_code == 404:
            return jsonify({"status": "error", "message": "El CUIT no existe en el padrón de AFIP."}), 404
        else:
            # Si el servicio falla, devolvemos un error controlado para que cargues manual
            return jsonify({"status": "error", "message": "Servidor de padrón ocupado. Ingrese los datos manualmente."}), 503

    except Exception as e:
        print(f"Error ARCA: {str(e)}")
        return jsonify({"status": "error", "message": "No hay conexión con el padrón nacional."}), 500
    
    
    
 # Asegúrate de importar CategoriaMovimiento

@admin_bp.route('/tesoreria')
@login_required
def tesoreria_dashboard():
    # 1. Traer las cajas
    fisicas = Caja.query.filter_by(tipo='FISICA').all()
    virtuales = Caja.query.filter_by(tipo='VIRTUAL').all()
    
    # 2. VERIFICACIÓN Y CARGA AUTOMÁTICA DE RUBROS
    lista_categorias = CategoriaMovimiento.query.all()
    
    if not lista_categorias:
        # Si la lista está vacía, creamos los rubros básicos automáticamente
        rubros_iniciales = [
            ('Logística: Fletes', 'EGRESO'),
            ('Logística: Comisionistas', 'EGRESO'),
            ('Servicios: Luz/Agua/Gas', 'EGRESO'),
            ('Personal: Sueldos', 'EGRESO'),
            ('Local: Alquiler', 'EGRESO'),
            ('Impuestos: AFIP/IIBB', 'EGRESO'),
            ('Ventas Extra', 'INGRESO'),
            ('Aporte de Capital', 'INGRESO')
        ]
        for nombre, tipo in rubros_iniciales:
            nueva_cat = CategoriaMovimiento(nombre=nombre, tipo=tipo)
            db.session.add(nueva_cat)
        db.session.commit()
        # Volvemos a consultar para que ahora sí tenga datos
        lista_categorias = CategoriaMovimiento.query.order_by(CategoriaMovimiento.nombre).all()
        print("Rubros de Vacan cargados automáticamente.")

    # 3. Totales para los cuadros
    total_efectivo = sum(c.saldo_actual for c in fisicas)
    total_virtual = sum(v.saldo_actual for v in virtuales)
    
    return render_template('admin/tesoreria.html', 
                           fisicas=fisicas, 
                           virtuales=virtuales,
                           categorias=lista_categorias, 
                           total_efectivo=total_efectivo,
                           total_virtual=total_virtual)
    
       

@admin_bp.route('/tesoreria/caja/<int:id>')
@login_required
def detalle_caja(id):
    caja = Caja.query.get_or_404(id)
    # Vemos los últimos 50 movimientos de esta caja
    movimientos = MovimientoFinanciero.query.filter_by(caja_id=id).order_by(MovimientoFinanciero.fecha.desc()).limit(50).all()
    return render_template('admin/caja_detalle.html', caja=caja, movimientos=movimientos)
    


@admin_bp.route('/tesoreria/nueva', methods=['POST'])
@login_required
@superadmin_required
def nueva_caja():
    nueva = Caja(
        nombre=request.form.get('nombre').upper(),
        tipo=request.form.get('tipo'),
        sucursal_id=current_user.sucursal_id,
        saldo_actual=0.0
    )
    db.session.add(nueva)
    db.session.commit()
    flash(f"Cuenta/Caja '{nueva.nombre}' habilitada.", "success")
    return redirect(url_for('admin.tesoreria_dashboard'))



#CHEQUES EN CARTERA

@admin_bp.route('/cheques')
@login_required
def cartera_cheques():
    hoy = date.today()
    # Solo mostramos los que están físicamente en la empresa
    #cheques = Cheque.query.filter_by(estado='EN_CARTERA').order_by(Cheque.fecha_vencimiento.asc()).all()
    cheques = Cheque.query.order_by(Cheque.fecha_vencimiento.asc()).all()
    # Traemos todas las cajas (físicas y virtuales) para que elijas destino
    cajas = Caja.query.all()
    
    return render_template('admin/cheques.html', cheques=cheques, hoy=hoy, cajas=cajas)

@admin_bp.route('/cheque/procesar/<int:id>', methods=['POST'])
@login_required
def procesar_cheque_pro(id):
    ch = Cheque.query.get_or_404(id)
    caja_destino_id = request.form.get('caja_id')
    accion = request.form.get('accion') # 'DEPOSITO' o 'COBRO_EFECTIVO'
    
    caja_destino = Caja.query.get(caja_destino_id)
    
    # 1. El cheque sale de la "Caja Origen" (donde se recibió originalmente)
    # Buscamos la caja física de la sucursal donde se cargó el cheque
    usuario_que_cargo = Usuario.query.get(ch.venta_asociada.usuario_id) if ch.venta_id else current_user
    caja_origen = Caja.query.filter_by(sucursal_id=usuario_que_cargo.sucursal_id, tipo='FISICA').first()

    if caja_origen and caja_destino:
        # Restamos el valor del "papel" de la caja donde estaba guardado
        caja_origen.saldo_actual -= ch.monto
        
        # Sumamos el valor a la caja donde entra el dinero real
        caja_destino.saldo_actual += ch.monto
        
        # Registramos el movimiento financiero
        motivo = f"{accion}: Cheque {ch.banco} N° {ch.numero}"
        mov = MovimientoFinanciero(
            caja_id=caja_destino.id,
            monto=ch.monto,
            tipo='INGRESO',
            motivo=motivo,
            metodo_detalle='EFECTIVO' if accion == 'COBRO_EFECTIVO' else 'TRANSFERENCIA',
            usuario_id=current_user.id
        )
        db.session.add(mov)
        
        # 2. Cambiamos el estado del cheque
        ch.estado = 'DEPOSITADO' if accion == 'DEPOSITO' else 'COBRADO'
        
        db.session.commit()
        flash(f"Valor procesado: ${ch.monto} acreditados en {caja_destino.nombre}", "success")
    else:
        flash("Error: No se pudo identificar la caja de origen o destino.", "danger")

    return redirect(url_for('admin.cartera_cheques'))


@admin_bp.route('/cheque/cambiar-estado/<int:id>/<string:nuevo_estado>')
@login_required
def cambiar_estado_cheque(id, nuevo_estado):
    ch = Cheque.query.get_or_404(id)
    ch.estado = nuevo_estado # 'DEPOSITADO' o 'ENTREGADO'
    db.session.commit()
    flash(f"El cheque de {ch.banco} fue marcado como {nuevo_estado}", "info")
    return redirect(url_for('admin.cartera_cheques'))


@admin_bp.route('/cheque/rechazar/<int:id>', methods=['POST'])
@login_required
def rechazar_cheque(id):
    ch = Cheque.query.get_or_404(id)
    gastos_bancarios = float(request.form.get('gastos') or 0)
    
    total_a_reclamar = ch.monto + gastos_bancarios

    # 1. REVERSAR EN TESORERÍA (Si estaba depositado o cobrado)
    if ch.estado in ['DEPOSITADO', 'COBRADO']:
        # Buscamos el movimiento original para saber de qué caja restar
        ultimo_mov = MovimientoFinanciero.query.filter(MovimientoFinanciero.motivo.contains(ch.numero)).order_by(MovimientoFinanciero.id.desc()).first()
        
        if ultimo_mov:
            caja = Caja.query.get(ultimo_mov.caja_id)
            caja.saldo_actual -= ch.monto 
            
            mov_egreso = MovimientoFinanciero(
                caja_id=caja.id,
                monto=-ch.monto,
                tipo='EGRESO',
                motivo=f"RECHAZO: Cheque {ch.banco} N° {ch.numero}",
                metodo_detalle='CHEQUE',
                usuario_id=current_user.id
            )
            db.session.add(mov_egreso)

    # 2. CARGAR LA DEUDA AL CLIENTE NUEVAMENTE (Corrección del SyntaxError aquí)
    nuevo_debito = MovimientoCtaCte(
        cliente_id=ch.cliente_id,
        monto=total_a_reclamar, # Aquí estaba el error del signo = extra
        tipo='DEUDA',
        descripcion=f"DÉBITO POR CHEQUE RECHAZADO N° {ch.numero} ({ch.banco})"
    )
    db.session.add(nuevo_debito)

    # 3. ACTUALIZAR ESTADO
    ch.estado = 'RECHAZADO'
    
    db.session.commit()
    flash(f"Cheque N°{ch.numero} rechazado. Se cargó la deuda al cliente.", "danger")
    return redirect(url_for('admin.cartera_cheques'))



#MOVIMIENTO MANUALES DE CAJA O CTAS VIRTUALES 
@admin_bp.route('/tesoreria/movimiento-manual', methods=['POST'])
@login_required
def movimiento_manual():
    caja_id = request.form.get('caja_id')
    tipo = request.form.get('tipo') # 'INGRESO' o 'EGRESO'
    monto = float(request.form.get('monto'))
    categoria_id = request.form.get('categoria_id')
    motivo = request.form.get('motivo')

    caja = Caja.query.get(caja_id)
    real_monto = monto if tipo == 'INGRESO' else -monto

    mov = MovimientoFinanciero(
        caja_id=caja.id,
        monto=monto,
        tipo=tipo,
        categoria_id=categoria_id,
        motivo=motivo,
        metodo_detalle='MANUAL',
        usuario_id=current_user.id
    )
    caja.saldo_actual += real_monto
    db.session.add(mov)
    db.session.commit()
    flash("Movimiento registrado correctamente", "success")
    return redirect(url_for('admin.tesoreria_dashboard'))

@admin_bp.route('/tesoreria/transferencia', methods=['POST'])
@login_required
def transferencia_fondos():
    origen_id = request.form.get('origen_id')
    destino_id = request.form.get('destino_id')
    monto = float(request.form.get('monto'))

    caja_origen = Caja.query.get(origen_id)
    caja_destino = Caja.query.get(destino_id)

    if caja_origen.saldo_actual < monto:
        flash("Fondos insuficientes en origen", "danger")
        return redirect(url_for('admin.tesoreria_dashboard'))

    # 1. Salida de origen
    mov_egreso = MovimientoFinanciero(
        caja_id=origen_id, monto=monto, tipo='EGRESO', 
        motivo=f"Transferencia a {caja_destino.nombre}", es_transferencia=True
    )
    caja_origen.saldo_actual -= monto

    # 2. Entrada a destino
    mov_ingreso = MovimientoFinanciero(
        caja_id=destino_id, monto=monto, tipo='INGRESO', 
        motivo=f"Transferencia desde {caja_origen.nombre}", es_transferencia=True
    )
    caja_destino.saldo_actual += monto

    db.session.add_all([mov_egreso, mov_ingreso])
    db.session.commit()
    flash("Transferencia realizada con éxito", "success")
    return redirect(url_for('admin.tesoreria_dashboard'))




@admin_bp.route('/tesoreria/cerrar-caja/<int:id>', methods=['POST'])
@login_required
def cerrar_caja(id):
    caja = Caja.query.get_or_404(id)
    saldo_real = float(request.form.get('saldo_real'))
    obs = request.form.get('observaciones')
    
    saldo_esperado = caja.saldo_actual
    diferencia = saldo_real - saldo_esperado
    
    # 1. Registramos el Cierre
    nuevo_cierre = CierreCaja(
        caja_id=caja.id,
        usuario_id=current_user.id,
        saldo_esperado=saldo_esperado,
        saldo_real=saldo_real,
        diferencia=diferencia,
        observaciones=obs
    )
    db.session.add(nuevo_cierre)
    
    # 2. Ajustamos el saldo de la caja a lo que realmente hay
    # Si faltaba plata, el saldo ahora baja a lo que el vendedor contó.
    caja.saldo_actual = saldo_real 
    
    # 3. Registramos un movimiento automático de ajuste si hubo diferencia
    if diferencia != 0:
        tipo_ajuste = 'INGRESO' if diferencia > 0 else 'EGRESO'
        mov_ajuste = MovimientoFinanciero(
            caja_id=caja.id,
            monto=abs(diferencia),
            tipo=tipo_ajuste,
            motivo=f"AJUSTE POR ARQUEO (Cierre #{caja.id})",
            metodo_detalle='AJUSTE',
            usuario_id=current_user.id
        )
        db.session.add(mov_ajuste)

    db.session.commit()
    
    color = "success" if diferencia == 0 else "warning"
    flash(f"Caja '{caja.nombre}' cerrada. Diferencia registrada: ${diferencia}", color)
    return redirect(url_for('admin.tesoreria_dashboard'))

@admin_bp.route('/tesoreria/historial-cierres')
@login_required
def historial_cierres():
    cierres = CierreCaja.query.order_by(CierreCaja.fecha_cierre.desc()).all()
    return render_template('admin/cierres_historial.html', cierres=cierres)



@admin_bp.route('/compras')
@login_required
def modulo_compras():
    # Necesitamos las sucursales para que el usuario elija dónde entra la mercadería
    proveedores = Proveedor.query.filter_by(activo=True).all()
    productos = Repuesto.query.all()
    sucursales = Sucursal.query.filter_by(activo=True).all() # <--- NUEVO
    
    return render_template('admin/compras.html', 
                           proveedores=proveedores, 
                           productos=productos, 
                           sucursales=sucursales)
    

# --- FUNCIÓN AUXILIAR PARA GENERAR SKU SECUENCIAL ---
def generar_proximo_sku_vacan():
    # Buscamos el último SKU que empiece con "VAC-"
    ultimo = Repuesto.query.filter(Repuesto.sku.like('VAC-%')).order_by(Repuesto.sku.desc()).first()
    
    if not ultimo:
        return "VAC-000001"
    
    try:
        # Extraemos la parte numérica (VAC-000001 -> 000001)
        partes = ultimo.sku.split('-')
        if len(partes) < 2: return "VAC-000001"
        
        numero_actual = int(partes[1])
        nuevo_numero = numero_actual + 1
        # Devolvemos con el formato de 6 ceros
        return f"VAC-{nuevo_numero:06d}"
    except:
        return "VAC-000001"

@admin_bp.route('/compras/procesar', methods=['POST'])
@login_required
def procesar_compra():
    if 'archivo_excel' in request.files:
        # --- LÓGICA EXCEL CON DESGLOSE FISCAL, MULTISUCURSAL Y NC/ND ---
        archivo = request.files['archivo_excel']
        prov_id = request.form.get('proveedor_id')
        nro_fact = request.form.get('nro_factura')
        plazo = int(request.form.get('plazo_pago', 30))
        suc_id = int(request.form.get('sucursal_id')) 
        margen = float(request.form.get('margen_sugerido', 30))
        
        tipo_comp = request.form.get('tipo_comprobante', 'FACTURA')
        signo_stock = -1 if tipo_comp == 'NC' else 1
        signo_finan = -1 if tipo_comp == 'NC' else 1
        
        iva_p = float(request.form.get('iva_porcentaje', 21))
        otros_imp = float(request.form.get('impuestos_monto', 0))
        
        try:
            df = pd.read_excel(archivo)
            df.columns = [c.lower().strip() for c in df.columns]
            
            nueva_compra = Compra(
                nro_factura=nro_fact, 
                proveedor_id=prov_id, 
                tipo_comprobante=tipo_comp,
                total=0,
                plazo_pago=plazo,
                iva_porcentaje=iva_p,
                impuestos_monto=otros_imp,
                margen_sugerido=margen
            )
            db.session.add(nueva_compra)
            db.session.flush()

            subtotal_items = 0
            for _, row in df.iterrows():
                raw_cod = str(row.get('codigo', '')).strip()
                nom = str(row.get('nombre', 'Producto Importado')).strip().upper()
                cant = int(row.get('cantidad', 0))
                cost = float(row.get('costo', 0))

                if not raw_cod or raw_cod.lower() == 'nan':
                    cod = generar_proximo_sku_vacan()
                else:
                    cod = raw_cod.upper()
                    if cod.endswith('.0'): cod = cod[:-2]

                rep = Repuesto.query.filter_by(sku=cod, sucursal_id=suc_id, proveedor_id=prov_id).first()

                if not rep:
                    rep = Repuesto(
                        sku=cod, nombre=nom, stock=0, costo=cost,
                        sucursal_id=suc_id, proveedor_id=prov_id,
                        precio=cost * (1 + (margen / 100)) 
                    )
                    db.session.add(rep)
                    db.session.flush()

                rep.stock += (cant * signo_stock)
                rep.costo = cost
                rep.precio = cost * (1 + (margen / 100))

                db.session.add(DetalleCompra(
                    compra=nueva_compra, repuesto=rep, nombre_item=rep.nombre,
                    cantidad=cant, costo_unitario=cost
                ))
                subtotal_items += (cant * cost)
                db.session.flush()

            total_final = (subtotal_items * (1 + (iva_p / 100)) + otros_imp) * signo_finan
            nueva_compra.subtotal = subtotal_items
            nueva_compra.total = total_final

            db.session.add(MovimientoCtaCteProveedor(
                proveedor_id=prov_id, monto=total_final, compra=nueva_compra, 
                descripcion=f"{tipo_comp} #{nro_fact} (Excel)"
            ))
            
            db.session.commit()
            flash(f"{tipo_comp} procesada con éxito. Total: ${total_final:,.2f}", "success")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('admin.modulo_compras'))

    else:
        # --- LÓGICA MANUAL (JSON) CON SOPORTE PARA AJUSTES DE SALDO (Punto 3) ---
        data = request.get_json()
        items = data.get('items')
        prov_id = data.get('proveedor_id')
        nro_fact = data.get('nro_factura')
        plazo = int(data.get('plazo_pago', 30))
        suc_id = int(data.get('sucursal_id'))
        margen = float(data.get('margen_sugerido', 30))
        
        tipo_comp = data.get('tipo_comprobante', 'FACTURA')
        signo_stock = -1 if tipo_comp == 'NC' else 1
        signo_finan = -1 if tipo_comp == 'NC' else 1
        
        subtotal_manual = float(data.get('subtotal', 0))
        iva_p = float(data.get('iva_porcentaje', 21))
        otros_imp = float(data.get('impuestos_monto', 0))
        total_final = (subtotal_manual * (1 + (iva_p / 100)) + otros_imp) * signo_finan
        
        try:
            nueva_compra = Compra(
                nro_factura=nro_fact, proveedor_id=prov_id, tipo_comprobante=tipo_comp,
                subtotal=subtotal_manual, iva_porcentaje=iva_p, impuestos_monto=otros_imp,
                total=total_final, plazo_pago=plazo, margen_sugerido=margen
            )
            db.session.add(nueva_compra)
            db.session.flush()

            for item in items:
                item_id = str(item['id'])
                costo_item = float(item['costo'])
                cant_item = int(item['cantidad'])
                
                id_repuesto_final = None
                
                # --- PUNTO 3: DETECCIÓN DE ÍTEM DE AJUSTE (S/STOCK) ---
                if item_id.startswith('ADJ_'):
                    # Es un ajuste (flete, interés, etc.): No buscamos repuesto ni tocamos stock
                    pass
                
                elif item_id.startswith('NEW_'):
                    # Es un alta nueva: Creamos el repuesto
                    sku_m = item_id.replace('NEW_', '').upper() or generar_proximo_sku_vacan()
                    rep = Repuesto(
                        sku=sku_m, nombre=item['nombre'].upper(), stock=0, 
                        costo=costo_item, sucursal_id=suc_id, proveedor_id=prov_id,
                        precio=costo_item * (1 + (margen / 100))
                    )
                    db.session.add(rep)
                    db.session.flush()
                    
                    rep.stock += (cant_item * signo_stock)
                    id_repuesto_final = rep.id
                else:
                    # Es un repuesto de stock existente
                    rep = Repuesto.query.get(item['id'])
                    if rep:
                        rep.stock += (cant_item * signo_stock)
                        rep.costo = costo_item
                        rep.precio = costo_item * (1 + (margen / 100))
                        id_repuesto_final = rep.id

                # Guardamos el detalle (Sea ajuste o repuesto)
                db.session.add(DetalleCompra(
                    compra=nueva_compra, 
                    repuesto_id=id_repuesto_final, 
                    nombre_item=item['nombre'].upper(),
                    cantidad=cant_item, 
                    costo_unitario=costo_item
                ))
                db.session.flush()

            db.session.add(MovimientoCtaCteProveedor(
                proveedor_id=prov_id, monto=total_final, compra=nueva_compra, 
                descripcion=f"{tipo_comp} #{nro_fact} (Manual)"
            ))
            
            db.session.commit()
            return jsonify({"status": "ok", "message": f"Operación exitosa por ${total_final:,.2f}"})

        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        



@admin_bp.route('/proveedores/devolucion-cheque/<int:id>', methods=['POST'])
@login_required
def devolver_cheque_cartera(id):
    ch = Cheque.query.get_or_404(id)
    prov_id = ch.proveedor_id 
    gastos = float(request.form.get('gastos') or 0)
    
    # El monto que vuelve a la deuda es el valor del cheque + gastos
    monto_reversion = ch.monto + gastos

    try:
        # 1. ACTUALIZAR CUENTA CORRIENTE DEL PROVEEDOR
        # Ahora que el modelo tiene 'tipo', esta línea ya no dará error
        reversion = MovimientoCtaCteProveedor(
            proveedor_id=prov_id,
            monto=monto_reversion, # Valor positivo SUMA deuda
            tipo='ND',             # Nota de Débito
            descripcion=f"REVERSIÓN PAGO: Devolución Cheque N°{ch.numero} ({ch.banco})"
        )
        db.session.add(reversion)

        # 2. DEVOLVER EL CHEQUE A LA CARTERA
        ch.estado = 'EN_CARTERA'
        ch.proveedor_id = None 
        ch.pago_prov_id = None 
        
        db.session.commit()
        flash(f"Cheque N°{ch.numero} reingresado a cartera. Se restauró la deuda con el proveedor.", "info")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al procesar la devolución: {str(e)}", "danger")

    return redirect(url_for('admin.cartera_cheques'))

@admin_bp.route('/cheques/reporte-historico')
@login_required
def reporte_historico_cheques():
    # 1. Captura de Filtros (Incluyendo Fechas)
    f_estado = request.args.get('estado')
    f_banco = request.args.get('banco')
    f_cliente = request.args.get('cliente_id', type=int) # <--- FILTRO DE CLIENTE
    f_inicio = request.args.get('inicio') # Fecha desde
    f_fin = request.args.get('fin')       # Fecha hasta
    query_busqueda = request.args.get('q', '').strip().lower()

    # 2. Consulta Base
    query = Cheque.query

    # 3. Aplicación de Filtros
    if f_estado:
        query = query.filter_by(estado=f_estado)
    if f_banco:
        query = query.filter(Cheque.banco.ilike(f"%{f_banco}%"))
    if f_cliente:
        query = query.filter_by(cliente_id=f_cliente) # <--- APLICADO
    if f_inicio:
        query = query.filter(Cheque.fecha_vencimiento >= datetime.strptime(f_inicio, '%Y-%m-%d').date())
    if f_fin:
        query = query.filter(Cheque.fecha_vencimiento <= datetime.strptime(f_fin, '%Y-%m-%d').date())
    if query_busqueda:
        query = query.filter(
            (Cheque.numero.contains(query_busqueda)) | 
            (Cheque.emisor.ilike(f"%{query_busqueda}%"))
        )

    cheques = query.order_by(Cheque.fecha_vencimiento.desc()).all()
    
    # 4. Estadísticas y Datos para Selectores
    stats = {
        'total_monto': sum(c.monto for c in cheques),
        'en_cartera': len([c for c in cheques if c.estado == 'EN_CARTERA']),
        'rechazados': len([c for c in cheques if c.estado == 'RECHAZADO']),
        'entregados': len([c for c in cheques if c.estado == 'ENTREGADO'])
    }
    bancos = db.session.query(Cheque.banco).distinct().all()

    return render_template('admin/reporte_cheques.html', 
                           cheques=cheques, 
                           stats=stats, 
                           bancos=[b[0] for b in bancos if b[0]],
                           hoy=get_argentina_time().date())
    
                  

@admin_bp.route('/proveedores/ajuste/<int:id>', methods=['POST'])
@login_required
def registrar_ajuste_proveedor(id):
    prov = Proveedor.query.get_or_404(id)
    tipo = request.form.get('tipo') # 'NC' o 'ND'
    motivo = request.form.get('motivo')
    monto = float(request.form.get('monto'))
    observaciones = request.form.get('observaciones')
    
    # En Cta Cte Proveedor: ND (+) sube deuda, NC (-) baja deuda
    monto_final = monto if tipo == 'ND' else -monto

    # 1. Crear el movimiento en la cuenta corriente
    nuevo_mov = MovimientoCtaCteProveedor(
        proveedor_id=id,
        monto=monto_final,
        tipo=tipo,
        descripcion=f"{tipo} - {motivo}: {observaciones}"
    )
    db.session.add(nuevo_mov)

    # 2. Lógica Especial: DEVOLUCIÓN DE MERCADERÍA (Solo para NC)
    if motivo == 'Devolución de Mercadería' and tipo == 'NC':
        sku_afectado = request.form.get('sku_devolucion')
        cantidad = int(request.form.get('cantidad_devolucion') or 0)
        if sku_afectado and cantidad > 0:
            # Buscamos el repuesto en la sucursal actual
            rep = Repuesto.query.filter_by(sku=sku_afectado, sucursal_id=current_user.sucursal_id).first()
            if rep:
                rep.stock -= cantidad # Descontamos del stock porque se lo lleva el camión
                flash(f"Se restaron {cantidad} unidades del stock de {rep.nombre}", "info")

    db.session.commit()
    flash(f"Nota de {tipo} registrada exitosamente.", "success")
    return redirect(url_for('admin.detalle_cta_cte_proveedor', id=id))


              
        
@admin_bp.route('/reportes/deudas-proveedores')
@login_required
def reporte_deudas_prov():
    filtro = request.args.get('filtro', 'vencidas') # 'vencidas' o 'proximas'
    hoy = get_argentina_time().date()
    
    # Buscamos compras con saldo pendiente (Total > Total Pagado)
    compras_pendientes = Compra.query.filter(Compra.total > Compra.total_pagado).all()
    
    reporte = []
    total_deuda_filtro = 0

    for c in compras_pendientes:
        # Usamos la propiedad 'fecha_vencimiento' que definimos en el modelo
        vencimiento_real = c.fecha_vencimiento
        dias_diferencia = (vencimiento_real - hoy).days
        
        es_vencida = dias_diferencia < 0
        
        # Filtramos según lo que el usuario quiera ver
        if (filtro == 'vencidas' and es_vencida) or (filtro == 'proximas' and not es_vencida):
            reporte.append({
                'compra': c,
                'proveedor': c.proveedor,
                'vencimiento': vencimiento_real,
                'dias_atraso': abs(dias_diferencia) if es_vencida else 0,
                'dias_restantes': dias_diferencia if not es_vencida else 0,
                'saldo': c.saldo_pendiente
            })
            total_deuda_filtro += c.saldo_pendiente

    # Ordenamos por fecha de vencimiento (más viejas primero)
    reporte.sort(key=lambda x: x['vencimiento'])

    return render_template('admin/reporte_deudas_prov.html', 
                           reporte=reporte, 
                           filtro=filtro, 
                           total=total_deuda_filtro,
                           hoy=hoy)        
 
@admin_bp.route('/proveedores/imprimir-pago/<int:movimiento_id>')
@login_required
def imprimir_pago_proveedor(movimiento_id):
    # Traemos el pago de la Cta Cte
    mov = MovimientoCtaCteProveedor.query.get_or_404(movimiento_id)
    
    # Gracias a la relación 'detalles_caja' y 'cheques_entregados' en el modelo, 
    # los datos ya viajan dentro del objeto 'mov'.
    
    return render_template('print/orden_pago.html', mov=mov)
# Asegúrate de tener estas funciones e imports en admin.py


def generar_proximo_sku_vacan():
    ultimo = Repuesto.query.filter(Repuesto.sku.like('VAC-%')).order_by(Repuesto.sku.desc()).first()
    if not ultimo:
        return "VAC-000001"
    try:
        partes = ultimo.sku.split('-')
        nuevo_numero = int(partes[1]) + 1
        return f"VAC-{nuevo_numero:06d}"
    except:
        return "VAC-000001"

@admin_bp.route('/inventario/carga-masiva', methods=['GET', 'POST'])
@login_required
def carga_masiva_stock():
    if request.method == 'POST':
        archivo = request.files.get('archivo_excel')
        if not archivo:
            flash("No se seleccionó ningún archivo.", "danger")
            return redirect(request.url)

        try:
            # Leemos el Excel con Pandas
            df = pd.read_excel(archivo)
            # Normalizamos nombres de columnas a minúsculas y sin espacios
            df.columns = [c.lower().strip() for c in df.columns]
            
            items_procesados = 0
            
            for _, row in df.iterrows():
                # --- 1. LIMPIEZA DE CÓDIGO (SOLUCIÓN AL .0 y NAN) ---
                raw_val = row.get('codigo')
                
                if pd.isna(raw_val) or str(raw_val).strip().lower() == 'nan' or str(raw_val).strip() == "":
                    cod = generar_proximo_sku_vacan() 
                else:
                    # Convertimos a texto y quitamos el .0 si Pandas lo tomó como float
                    cod = str(raw_val).strip()
                    if cod.endswith('.0'):
                        cod = cod[:-2]
                    cod = cod.upper()

                # --- 2. CAPTURA DE CAMPOS ---
                nom = str(row.get('nombre', 'PRODUCTO NUEVO')).strip().upper()
                s_vacan = str(row.get('sku_vacan', '')).strip().upper() if not pd.isna(row.get('sku_vacan')) else None
                rub = str(row.get('rubro', '')).strip().upper() if not pd.isna(row.get('rubro')) else "GENERAL"
                sub = str(row.get('subrubro', '')).strip().upper() if not pd.isna(row.get('subrubro')) else "GENERAL"
                
                # Sucursal: ID del local (Default: 1)
                suc_id = row.get('sucursal_id')
                suc_id = int(float(suc_id)) if not pd.isna(suc_id) else 1

                # Proveedor: ID del proveedor (Default: 1 o lo que indiques en el Excel)
                prov_id = row.get('proveedor_id')
                prov_id = int(float(prov_id)) if not pd.isna(prov_id) else None

                # Valores económicos
                cant = int(row.get('stock', 0)) if not pd.isna(row.get('stock')) else 0
                cost = float(row.get('costo', 0)) if not pd.isna(row.get('costo')) else 0.0
                prec = float(row.get('precio', 0)) if not pd.isna(row.get('precio')) else 0.0

                # --- 3. BUSCADOR INTELIGENTE (COINCIDENCIA TRIPLE) ---
                # Buscamos por SKU + SUCURSAL + PROVEEDOR
                rep = Repuesto.query.filter_by(
                    sku=cod, 
                    sucursal_id=suc_id, 
                    proveedor_id=prov_id
                ).first()

                if not rep:
                    # --- 4. AUTO-ALTA (Si no existe esta combinación exacta) ---
                    rep = Repuesto(
                        sku=cod,
                        sku_vacan=s_vacan or generar_proximo_sku_vacan(),
                        nombre=nom,
                        rubro=rub,
                        subrubro=sub,
                        sucursal_id=suc_id,
                        proveedor_id=prov_id, # Asociamos al proveedor
                        stock=cant,
                        costo=cost,
                        precio=prec if prec > 0 else (cost * 1.35)
                    )
                    db.session.add(rep)
                    db.session.flush() 
                    
                    # Registro inicial en historial
                    hist = HistorialPrecio(
                        repuesto=rep, 
                        costo_anterior=0, costo_nuevo=cost,
                        precio_anterior=0, precio_nuevo=rep.precio, 
                        usuario_id=current_user.id
                    )
                    db.session.add(hist)
                else:
                    # --- 5. SUMA AUTOMÁTICA DE STOCK (Misma combinación encontrada) ---
                    if rep.costo != cost or (prec > 0 and rep.precio != prec):
                        hist = HistorialPrecio(
                            repuesto=rep,
                            costo_anterior=rep.costo, costo_nuevo=cost,
                            precio_anterior=rep.precio, precio_nuevo=prec if prec > 0 else rep.precio,
                            usuario_id=current_user.id
                        )
                        db.session.add(hist)
                    
                    # SUMAMOS la cantidad nueva a la existente
                    rep.stock += cant 
                    
                    # Actualizamos el resto de la información
                    rep.costo = cost
                    if prec > 0: rep.precio = prec
                    rep.rubro = rub
                    rep.subrubro = sub
                    if s_vacan: rep.sku_vacan = s_vacan

                items_procesados += 1
                db.session.flush() 

            db.session.commit()
            flash(f"¡Éxito! Se procesaron {items_procesados} artículos. El stock fue sumado para coincidencias de proveedor.", "success")
            return redirect(url_for('inventory.index'))

        except Exception as e:
            db.session.rollback()
            print(f"Error en Carga Masiva: {str(e)}") 
            flash(f"Error al procesar el Excel: {str(e)}", "danger")
            return redirect(url_for('admin.carga_masiva_stock'))

    return render_template('admin/inventario_masivo.html')



# Función auxiliar para convertir HTML a PDF
def render_pdf(template_src, context_dict):
    html = render_template(template_src, **context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None

@admin_bp.route('/exportar/remito/<int:id>')
@login_required
def pdf_remito(id):
    venta = Venta.query.get_or_404(id)
    pdf = render_pdf('print/remito_pdf.html', {'venta': venta})
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=Remito_Vacan_{id}.pdf'
    return response

@admin_bp.route('/exportar/recibo/<int:mov_id>')
@login_required
def pdf_recibo(mov_id):
    mov = MovimientoCtaCte.query.get_or_404(mov_id)
    pdf = render_pdf('print/recibo_pdf.html', {'m': mov})
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=Recibo_Vacan_{mov_id}.pdf'
    return response


@admin_bp.route('/traspasos')
@login_required
def modulo_traspasos():
    sucursales = Sucursal.query.filter_by(activo=True).all()
    # Enviamos los traspasos realizados para el historial
    historial = Traspaso.query.order_by(Traspaso.fecha.desc()).all()
    return render_template('admin/traspasos.html', sucursales=sucursales, historial=historial)

@admin_bp.route('/traspasos/obtener-stock/<int:sucursal_id>')
@login_required
def obtener_stock_sucursal(sucursal_id):
    # Capturamos el término de búsqueda que viene del buscador
    query = request.args.get('q', '').strip().lower()
    
    if len(query) < 2:
        return jsonify([]) # No devolvemos nada si la búsqueda es muy corta

    search_term = f"%{query}%"
    
    # Buscamos SOLO en esa sucursal y SOLO lo que coincida con el nombre o SKU
    productos = Repuesto.query.filter_by(sucursal_id=sucursal_id).filter(
        (Repuesto.nombre.ilike(search_term)) | 
        (Repuesto.sku.ilike(search_term))
    ).filter(Repuesto.stock > 0).limit(20).all() # Limitamos a 20 resultados para velocidad total

    return jsonify([{'id': p.id, 'nombre': p.nombre, 'sku': p.sku, 'stock': p.stock} for p in productos])


@admin_bp.route('/traspasos/procesar', methods=['POST'])
@login_required
def procesar_traspaso():
    data = request.get_json()
    origen_id = int(data.get('origen_id'))
    destino_id = int(data.get('destino_id'))
    items = data.get('items')

    if origen_id == destino_id:
        return jsonify({"status": "error", "message": "Origen y destino no pueden ser iguales"}), 400

    try:
        nuevo_traspaso = Traspaso(
            sucursal_origen_id=origen_id,
            sucursal_destino_id=destino_id,
            usuario_id=current_user.id,
            observaciones=data.get('observaciones')
        )
        db.session.add(nuevo_traspaso)
        db.session.flush()

        for item in items:
            # 1. Repuesto en Origen
            rep_origen = Repuesto.query.get(item['id'])
            cant = int(item['cantidad'])
            
            if rep_origen.stock < cant:
                raise Exception(f"Stock insuficiente de {rep_origen.nombre} en origen.")

            # 2. Buscar o Crear en Destino (Fusión Inteligente)
            rep_destino = Repuesto.query.filter_by(sku=rep_origen.sku, sucursal_id=destino_id).first()
            
            if not rep_destino:
                # Clonamos el producto en la sucursal de destino si no existía
                rep_destino = Repuesto(
                    sku=rep_origen.sku, sku_vacan=rep_origen.sku_vacan,
                    nombre=rep_origen.nombre, rubro=rep_origen.rubro,
                    subrubro=rep_origen.subrubro, costo=rep_origen.costo,
                    precio=rep_origen.precio, sucursal_id=destino_id,
                    proveedor_id=rep_origen.proveedor_id, stock=0
                )
                db.session.add(rep_destino)
                db.session.flush()

            # 3. Mover las cantidades
            rep_origen.stock -= cant
            rep_destino.stock += cant
            
            # 4. Registrar detalle del traspaso
            detalle = DetalleTraspaso(traspaso_id=nuevo_traspaso.id, repuesto_id=rep_origen.id, cantidad=cant)
            db.session.add(detalle)

        db.session.commit()
        return jsonify({"status": "ok", "traspaso_id": nuevo_traspaso.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    





@admin_bp.route('/reportes/rentabilidad-premium')
@login_required
def reporte_rentabilidad():
    # 1. GESTIÓN DE FECHAS (Periodo Actual y Anterior)
    desde_str = request.args.get('desde', date.today().replace(day=1).strftime('%Y-%m-%d'))
    hasta_str = request.args.get('hasta', date.today().strftime('%Y-%m-%d'))
    
    desde = datetime.strptime(desde_str, '%Y-%m-%d')
    hasta = datetime.strptime(hasta_str, '%Y-%m-%d')
    
    # Calculamos la duración del periodo para comparar con el periodo anterior exacto
    dias_periodo = (hasta - desde).days + 1
    ant_desde = desde - timedelta(days=dias_periodo)
    ant_hasta = desde - timedelta(days=1)

    sucursales = Sucursal.query.filter_by(activo=True).all()
    reporte_sucursales = []
    
    # --- TOTALES GLOBALES (INICIALIZACIÓN) ---
    g_stock_costo = 0
    g_stock_venta = 0
    g_ventas = 0
    g_compras = 0
    g_cobranzas = 0
    g_gastos = 0
    g_iva_v = 0

    # --- PROCESAMIENTO POR SUCURSAL ---
    for suc in sucursales:
        # Stock Valorizado
        s_costo = db.session.query(func.sum(Repuesto.stock * Repuesto.costo)).filter_by(sucursal_id=suc.id).scalar() or 0
        s_venta = db.session.query(func.sum(Repuesto.stock * Repuesto.precio)).filter_by(sucursal_id=suc.id).scalar() or 0
        
        # Ventas del periodo
        ventas_suc = Venta.query.filter_by(sucursal_id=suc.id).filter(Venta.fecha.between(desde_str + " 00:00:00", hasta_str + " 23:59:59")).all()
        s_ventas = sum(v.total for v in ventas_suc)
        s_iva_v = sum(v.total - (v.total / 1.21) for v in ventas_suc)

        # Compras (Mercadería ingresada a esta sucursal)
        s_compras = db.session.query(func.sum(Compra.total)).join(DetalleCompra).join(Repuesto).filter(
            Repuesto.sucursal_id == suc.id,
            Compra.fecha.between(desde_str, hasta_str)
        ).scalar() or 0
        
        # Gastos Operativos de la sucursal
        s_gastos = db.session.query(func.sum(MovimientoFinanciero.monto)).join(Caja).filter(
            Caja.sucursal_id == suc.id,
            MovimientoFinanciero.tipo == 'EGRESO',
            MovimientoFinanciero.fecha.between(desde_str, hasta_str)
        ).scalar() or 0

        # Cobranzas (Ingresos de Cta Cte)
        s_cobranzas = db.session.query(func.sum(MovimientoFinanciero.monto)).join(Caja).filter(
            Caja.sucursal_id == suc.id,
            MovimientoFinanciero.tipo == 'INGRESO',
            MovimientoFinanciero.motivo.contains('Cobranza'),
            MovimientoFinanciero.fecha.between(desde_str, hasta_str)
        ).scalar() or 0

        reporte_sucursales.append({
            'nombre': suc.nombre,
            'stock_costo': s_costo,
            'ventas': s_ventas,
            'gastos': s_gastos,
            'cobranzas': s_cobranzas,
            'utilidad': s_ventas - s_gastos
        })

        g_stock_costo += s_costo
        g_stock_venta += s_venta
        g_ventas += s_ventas
        g_compras += s_compras
        g_cobranzas += s_cobranzas
        g_gastos += s_gastos
        g_iva_v += s_iva_v

    # --- LÓGICA COMPARATIVA (PERIODO ANTERIOR) ---
    ant_ventas = db.session.query(func.sum(Venta.total)).filter(Venta.fecha.between(ant_desde, ant_hasta)).scalar() or 0
    ant_compras = db.session.query(func.sum(Compra.total)).filter(Compra.fecha.between(ant_desde, ant_hasta)).scalar() or 0

    # --- SALDOS DE CUENTA CORRIENTE (LIQUIDEZ) ---
    total_cta_cte_clientes = db.session.query(func.sum(MovimientoCtaCte.monto)).scalar() or 0
    total_cta_cte_prov = db.session.query(func.sum(MovimientoCtaCteProveedor.monto)).scalar() or 0

    # Ranking de productos (Top 5)
    ranking = db.session.query(Repuesto.nombre, func.sum(DetalleVenta.cantidad).label('total'))\
        .join(DetalleVenta).join(Venta).filter(Venta.fecha.between(desde_str, hasta_str))\
        .group_by(Repuesto.id).order_by(text('total DESC')).limit(5).all()

    total_rechazados = db.session.query(func.sum(Cheque.monto)).filter_by(estado='RECHAZADO').scalar() or 0

    return render_template('admin/reporte_premium.html',
                           desde=desde_str, hasta=hasta_str,
                           sucursales_data=reporte_sucursales,
                           g_stock_costo=g_stock_costo,
                           g_stock_venta=g_stock_venta,
                           g_ventas=g_ventas,
                           g_compras=g_compras,
                           g_cobranzas=g_cobranzas,
                           g_gastos=g_gastos,
                           g_iva_v=g_iva_v,
                           total_rechazados=total_rechazados,
                           ranking=ranking,
                           ant_ventas=ant_ventas,
                           ant_compras=ant_compras,
                           total_clientes=total_cta_cte_clientes,
                           total_prov=total_cta_cte_prov)