import os

class Config:
    # BASE_DIR obtiene la ruta absoluta de la carpeta donde se encuentra este archivo.
    # Esto es vital para que PythonAnywhere encuentre la base de datos sin errores.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # 1. Cambiamos el nombre a 'vacan.bd' como solicitaste.
    # 2. Al usar os.path.join con BASE_DIR, garantizamos una ruta absoluta (ej: /home/Walter.../vacan.bd).
    # 3. El prefijo 'sqlite:///' sumado a una ruta que empieza con '/' genera las 4 barras necesarias en Linux.
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'vacan.bd')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Usamos una variable de entorno para la clave secreta si existe, sino la de desarrollo.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar-vacan-2024'
    
    TIMEZONE = 'America/Argentina/Buenos_Aires'