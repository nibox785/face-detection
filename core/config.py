import os

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
SECRET_KEY = os.getenv('SECRET_KEY', 'face-attendance-secret-key')
ACCESS_TOKEN_EXPIRE_SECONDS = int(os.getenv('ACCESS_TOKEN_EXPIRE_SECONDS', '3600'))
