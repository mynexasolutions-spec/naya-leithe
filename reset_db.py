import os
from flask import Flask
from models import db
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    print("Dropping all tables on Supabase...")
    db.drop_all()
    print("Recreating tables with new limits...")
    db.create_all()
    print("Done! You can now run seed_db.py")
