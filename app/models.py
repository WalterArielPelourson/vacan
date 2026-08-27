from app import db
from flask_login import UserMixin
from datetime import datetime
import pytz

# --- CONFIGURACIÓN ---
def get_argentina_time():
    argentina_tz = pytz.timezone('America/Argentina/Buenos_Aires')
    return datetime.now(argentina_tz)

compatibilidad = db.Table('compatibilidad',
    db.Column('repuesto_id', db.Integer, db.ForeignKey('repuesto.id'), primary_key=True),
    db.Column('modelo_auto_id', db.Integer, db.ForeignKey('modelo_auto.id'), primary_key=True)
)

# --- EMPRESA Y SUCURSALES ---
class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    cuit = db.Column(db.String(20), unique=True)
    sucursales = db.relationship('Sucursal', back_populates='empresa')

class Sucursal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    cuit = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    localidad = db.Column(db.String(100))
    provincia = db.Column(db.String(100))
    celular = db.Column(db.String(20))
    celular_alternativo = db.Column(db.String(20))
    activo = db.Column(db.Boolean, default=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'))

    empresa = db.relationship('Empresa', back_populates='sucursales')
    usuarios = db.relationship('Usuario', back_populates='sucursal')
    
    # --- RELACIONES CORREGIDAS ---
    ventas = db.relationship('Venta', back_populates='sucursal')
    stock_items = db.relationship('Repuesto', back_populates='sucursal') # Nombre único para stock
    cajas = db.relationship('Caja', back_populates='sucursal')
    
    
    
# --- USUARIOS ---
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    rol = db.Column(db.String(20), default='vendedor')
    activo = db.Column(db.Boolean, default=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    
    sucursal = db.relationship('Sucursal', back_populates='usuarios')
    ventas = db.relationship('Venta', back_populates='usuario')
    ajustes_precios = db.relationship('HistorialPrecio', back_populates='usuario')

    cierres_realizados = db.relationship('CierreCaja', back_populates='usuario_rel')
    
# --- CONTACTOS ---
class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    razon_social = db.Column(db.String(150), nullable=False)
    cuit = db.Column(db.String(20), unique=True)
    condicion_iva = db.Column(db.String(50))
    direccion = db.Column(db.String(200))
    localidad = db.Column(db.String(100))
    provincia = db.Column(db.String(100))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    iibb = db.Column(db.String(50))
    activo = db.Column(db.Boolean, default=True)

    ventas = db.relationship('Venta', back_populates='cliente')
    movimientos_cta = db.relationship('MovimientoCtaCte', back_populates='cliente')

class Proveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    razon_social = db.Column(db.String(150), nullable=False)
    cuit = db.Column(db.String(20), unique=True)
    condicion_iva = db.Column(db.String(50))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(50))
    iibb = db.Column(db.String(50))
    activo = db.Column(db.Boolean, default=True)

    compras = db.relationship('Compra', back_populates='proveedor')
    movimientos_p = db.relationship('MovimientoCtaCteProveedor', back_populates='proveedor')

# --- STOCK ---
class Repuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), nullable=False)
    sku_vacan = db.Column(db.String(50))
    codigo_oem = db.Column(db.String(100))
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    stock = db.Column(db.Integer, default=0)
    precio = db.Column(db.Float, default=0.0)
    costo = db.Column(db.Float, default=0.0)
    rubro = db.Column(db.String(100))
    subrubro = db.Column(db.String(100))
    ubicacion = db.Column(db.String(100), nullable=True) 
    
    # Auxiliares
    sku_denso = db.Column(db.String(50))
    sku_cromosol = db.Column(db.String(50))
    sku_expoyer = db.Column(db.String(50))
    sku_repuestos_jl = db.Column(db.String(50))
    sku_facor = db.Column(db.String(50))
    sku_altri = db.Column(db.String(50))
    sku_rosparts = db.Column(db.String(50))
    otros_codigos = db.Column(db.Text)

    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    proveedor = db.relationship('Proveedor', backref='productos_suministrados')
    
    # --- VÍNCULO CORREGIDO ---
    # Apunta a 'stock_items' en lugar de 'ventas'
    sucursal = db.relationship('Sucursal', back_populates='stock_items') 
    
    autos_compatibles = db.relationship('ModeloAuto', secondary=compatibilidad, backref='repuestos_compatibles')
    historial_precios = db.relationship('HistorialPrecio', back_populates='repuesto', cascade="all, delete-orphan")
    
    
    
    
    
class HistorialPrecio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    repuesto_id = db.Column(db.Integer, db.ForeignKey('repuesto.id'), nullable=False)
    costo_anterior = db.Column(db.Float)
    costo_nuevo = db.Column(db.Float)
    precio_anterior = db.Column(db.Float)
    precio_nuevo = db.Column(db.Float)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    
    repuesto = db.relationship('Repuesto', back_populates='historial_precios')
    usuario = db.relationship('Usuario', back_populates='ajustes_precios')

class ModeloAuto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(50), nullable=False)
    modelo = db.Column(db.String(50), nullable=False)
    anio_inicio = db.Column(db.Integer)
    anio_fin = db.Column(db.Integer)

# --- VENTAS ---
class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    total = db.Column(db.Float, nullable=False)
    tipo_comprobante = db.Column(db.String(20), default='REMITO')
    metodo_pago = db.Column(db.String(20))
    estado_arca = db.Column(db.String(20), default='PENDIENTE')
    esta_pagada = db.Column(db.Boolean, default=False)
    total_pagado = db.Column(db.Float, default=0.0)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    
    cliente = db.relationship('Cliente', back_populates='ventas')
    usuario = db.relationship('Usuario', back_populates='ventas')
    
    # --- VÍNCULO MANTENIDO ---
    # Este usa 'ventas' correctamente
    sucursal = db.relationship('Sucursal', back_populates='ventas')
    
    detalles = db.relationship('DetalleVenta', back_populates='venta', cascade="all, delete-orphan")
    pagos = db.relationship('PagoVenta', back_populates='venta', cascade="all, delete-orphan")
    movimientos_cta = db.relationship('MovimientoCtaCte', back_populates='venta')
    
    
class DetalleVenta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey('repuesto.id'), nullable=True)
    nombre_item = db.Column(db.String(200))
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    
    venta = db.relationship('Venta', back_populates='detalles')
    repuesto = db.relationship('Repuesto')

class PagoVenta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=False)
    metodo = db.Column(db.String(50))
    monto = db.Column(db.Float, nullable=False)
    banco = db.Column(db.String(100))
    nro_comprobante = db.Column(db.String(100))
    cuotas = db.Column(db.Integer, default=1)
    interes = db.Column(db.Float, default=0.0)
    
    venta = db.relationship('Venta', back_populates='pagos')

# --- COMPRAS ---
class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    tipo_comprobante = db.Column(db.String(20), default='FACTURA') # 'FACTURA', 'NC', 'ND'
    nro_factura = db.Column(db.String(50))
    subtotal = db.Column(db.Float, default=0.0)
    iva_porcentaje = db.Column(db.Float, default=21.0) # 21%, 10.5%, etc.
    impuestos_monto = db.Column(db.Float, default=0.0) # Percepciones IIBB, Gananc
    total = db.Column(db.Float, nullable=False)
    plazo_pago = db.Column(db.Integer, default=30)
    margen_sugerido = db.Column(db.Float, default=30.0) # Porcentaje (ej: 35.5)
    total_pagado = db.Column(db.Float, default=0.0)
    esta_pagada = db.Column(db.Boolean, default=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    
    proveedor = db.relationship('Proveedor', back_populates='compras')
    detalles = db.relationship('DetalleCompra', back_populates='compra', cascade="all, delete-orphan")
    movimiento_cta = db.relationship('MovimientoCtaCteProveedor', back_populates='compra', uselist=False)

    @property
    def saldo_pendiente(self):
        return round(self.total - self.total_pagado, 2)
    @property
    def fecha_vencimiento(self):
        from datetime import timedelta
        return (self.fecha + timedelta(days=self.plazo_pago)).date()

class DetalleCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey('repuesto.id'), nullable=True)
    nombre_item = db.Column(db.String(200))
    cantidad = db.Column(db.Integer, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False)
    
    compra = db.relationship('Compra', back_populates='detalles')
    repuesto = db.relationship('Repuesto')

class MovimientoCtaCteProveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200))
    referencia = db.Column(db.String(50))
    # --- ESTA ES LA COLUMNA QUE FALTA ---
    tipo = db.Column(db.String(20), default='COMPRA') # 'COMPRA', 'PAGO', 'NC', 'ND'
    # ------------------------------------
    pago_prov_id = db.Column(db.Integer, db.ForeignKey('movimiento_cta_cte_proveedor.id'), nullable=True)

    sucursal = db.relationship('Sucursal')
    proveedor = db.relationship('Proveedor', back_populates='movimientos_p')
    compra = db.relationship('Compra', back_populates='movimiento_cta')
    detalles_pago = db.relationship('MovimientoFinanciero', back_populates='pago_maestro')
    cheques_pago = db.relationship('Cheque', back_populates='pago_maestro')

    
# --- TESORERÍA ---
class Caja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    saldo_actual = db.Column(db.Float, default=0.0)
    tipo = db.Column(db.String(20))

    sucursal = db.relationship('Sucursal', back_populates='cajas')
    movimientos = db.relationship('MovimientoFinanciero', back_populates='caja')
    cierres = db.relationship('CierreCaja', back_populates='caja')

class CategoriaMovimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(10))

class MovimientoFinanciero(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    caja_id = db.Column(db.Integer, db.ForeignKey('caja.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(10)) 
    motivo = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    metodo_detalle = db.Column(db.String(50))
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_movimiento.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    pago_prov_id = db.Column(db.Integer, db.ForeignKey('movimiento_cta_cte_proveedor.id'), nullable=True)
    es_transferencia = db.Column(db.Boolean, default=False)
    referencia = db.Column(db.String(50))
    
    caja = db.relationship('Caja', back_populates='movimientos')
    pago_maestro = db.relationship('MovimientoCtaCteProveedor', back_populates='detalles_pago')
    categoria = db.relationship('CategoriaMovimiento')

class CierreCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    caja_id = db.Column(db.Integer, db.ForeignKey('caja.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_cierre = db.Column(db.DateTime, default=get_argentina_time)
    saldo_esperado = db.Column(db.Float, nullable=False)
    saldo_real = db.Column(db.Float, nullable=False)
    diferencia = db.Column(db.Float, nullable=False)
    observaciones = db.Column(db.Text)
    
    # RELACIONES LIMPIAS
    caja = db.relationship('Caja', back_populates='cierres')
    # Esta es la que soluciona el error:
    usuario_rel = db.relationship('Usuario', back_populates='cierres_realizados')

# --- VALORES ---
class Cheque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    banco = db.Column(db.String(100), nullable=False)
    numero = db.Column(db.String(50), nullable=False)
    emisor = db.Column(db.String(150))
    monto = db.Column(db.Float, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(20))
    estado = db.Column(db.String(20), default='EN_CARTERA')
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    pago_prov_id = db.Column(db.Integer, db.ForeignKey('movimiento_cta_cte_proveedor.id'), nullable=True)


    # --- ESTA ES LA RELACIÓN QUE FALTA (Punto clave) ---
    # Permite que el HTML haga: ch.proveedor.razon_social
    proveedor = db.relationship('Proveedor', backref='cheques_entregados_prov')
    
    pago_prov_obj = db.relationship('MovimientoCtaCteProveedor', backref='cheques_list_info')
    pago_maestro = db.relationship('MovimientoCtaCteProveedor', back_populates='cheques_pago')

class MovimientoCtaCte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    descripcion = db.Column(db.String(200))
    monto = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(20))
    
    sucursal = db.relationship('Sucursal') # Relación para el filtro
    venta = db.relationship('Venta', back_populates='movimientos_cta')
    cliente = db.relationship('Cliente', back_populates='movimientos_cta')

# --- PRESUPUESTOS ---
class Presupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    total = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(20), default='PENDIENTE')
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    
    detalles = db.relationship('DetallePresupuesto', back_populates='presupuesto', cascade="all, delete-orphan")

class DetallePresupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    presupuesto_id = db.Column(db.Integer, db.ForeignKey('presupuesto.id'), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey('repuesto.id'), nullable=True)
    nombre_item = db.Column(db.String(200))
    cantidad = db.Column(db.Integer, nullable=False)
    precio_pactado = db.Column(db.Float, nullable=False)
    
    presupuesto = db.relationship('Presupuesto', back_populates='detalles')
    repuesto = db.relationship('Repuesto')
    
    
    
    
# --- MÓDULO DE TRASPASOS ---
class Traspaso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=get_argentina_time)
    sucursal_origen_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=False)
    sucursal_destino_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    observaciones = db.Column(db.String(200))

    # Relaciones
    origen = db.relationship('Sucursal', foreign_keys=[sucursal_origen_id])
    destino = db.relationship('Sucursal', foreign_keys=[sucursal_destino_id])
    usuario = db.relationship('Usuario')
    detalles = db.relationship('DetalleTraspaso', backref='traspaso_rel', lazy=True)

class DetalleTraspaso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    traspaso_id = db.Column(db.Integer, db.ForeignKey('traspaso.id'), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey('repuesto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    
    repuesto = db.relationship('Repuesto')