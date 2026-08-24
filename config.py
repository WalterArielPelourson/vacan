import os

class Config:
    
    # Ubicación de la base de datos (un archivo llamado vacan.db)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'vacan.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'una-clave-secreta-muy-dificil-de-adivinar'
    TIMEZONE = 'America/Argentina/Buenos_Aires'