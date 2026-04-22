import os
from app import app
from models import db

with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database schema recreated successfully in " + app.config['SQLALCHEMY_DATABASE_URI'])
