import os
from flask import Flask
from models import db

app = Flask(__name__)
# Force local SQLite path
db_path = os.path.join(app.instance_path, 'site.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

db.init_app(app)

with app.app_context():
    db.drop_all()
    db.create_all()
    print(f"Local SQLite schema recreated successfully in {db_path}")
