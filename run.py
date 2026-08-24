import os
import time
from app import create_app

# Configuración de zona horaria a nivel sistema operativo
# Esto es vital para servidores en el extranjero como PythonAnywhere
os.environ['TZ'] = 'America/Argentina/Buenos_Aires'
if hasattr(time, 'tzset'):
    time.tzset()

app = create_app()

# Crear carpeta de subidas si no existe
if not os.path.exists('uploads'):
    os.makedirs('uploads')

if __name__ == '__main__':
    # El modo debug=True es solo para desarrollo local
    app.run(debug=True)