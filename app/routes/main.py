from flask import Blueprint, render_template, request
from app.models import Repuesto, Sucursal

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    # Buscamos el celular de la sucursal principal (ID 1 o la primera que encuentre)
    sucursal = Sucursal.query.first()
    # Limpiamos el número de símbolos (+, -, espacios) para que WhatsApp lo entienda
    whatsapp_num = sucursal.celular.replace("+","").replace("-","").replace(" ","") if sucursal and sucursal.celular else "549" 
    
    destacados = Repuesto.query.limit(4).all()
    return render_template('public/home.html', destacados=destacados, whatsapp=whatsapp_num)

@main_bp.route('/catalogo-publico')
def catalogo_publico():
    query = request.args.get('q', '')
    sucursal = Sucursal.query.first()
    whatsapp_num = sucursal.celular.replace("+","").replace("-","").replace(" ","") if sucursal and sucursal.celular else "549"

    if query:
        resultados = Repuesto.query.filter(Repuesto.nombre.contains(query)).all()
    else:
        resultados = Repuesto.query.all()
        
    return render_template('public/catalogo.html', productos=resultados, whatsapp=whatsapp_num)