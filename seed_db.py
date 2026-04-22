import os
from flask import Flask
from models import db, Category, Product, SubCategory
from dotenv import load_dotenv

load_dotenv()

# Create a temporary app to initialize the database
app = Flask(__name__)

# Database Configuration
db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise RuntimeError("DATABASE_URL not found in environment variables")
elif db_url.startswith("postgres://"):
    # Fix for newer SQLAlchemy/Heroku/Vercel postgres URLs
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Updated Category Structure (Sarees in Ethnic, Jewellery in Accessories)
categories_data = [
    { 
        "name": "Western Wear", 
        "img": "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=800&q=80", 
        "bg": "#f8e1e7", 
        "subcategories": ["Jeans", "Tops", "Dresses", "Cord Sets"] 
    },
    { 
        "name": "Ethnic Wear", 
        "img": "https://images.unsplash.com/photo-1610030469668-301755255018?w=800&q=80", 
        "bg": "#fdf0d5", 
        "subcategories": ["Suits", "Cotton 2-Piece Sets", "Lehenga Choli", "Sarees", "Blouses"] 
    },
    { 
        "name": "Accessories", 
        "img": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=800&q=80", 
        "bg": "#a8c0ba", 
        "subcategories": ["Bags & Purses", "Belts", "Scarves", "Jewellery"] 
    },
]

all_products = [
    # Ethnic Wear (3)
    {"id": "eth1", "name": "Emerald Silk Saree", "cat": "Ethnic Wear", "sub": "Sarees", "price": "3,499", "orig": "4,200", "badge": "New", "img": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=500&q=80", "is_featured": True},
    {"id": "eth2", "name": "Midnight Suit Set", "cat": "Ethnic Wear", "sub": "Suits", "price": "1,999", "orig": "2,400", "badge": "Trending", "img": "https://images.unsplash.com/photo-1610030469668-301755255018?w=500&q=80", "is_featured": True},
    {"id": "eth3", "name": "Royal Lehenga Choli", "cat": "Ethnic Wear", "sub": "Lehenga Choli", "price": "5,999", "orig": "7,500", "badge": "Premium", "img": "https://images.unsplash.com/photo-1583391733956-6c78276477e2?w=500&q=80", "is_featured": False},
    
    # Western Wear (3)
    {"id": "west1", "name": "Floral Gown Set", "cat": "Western Wear", "sub": "Dresses", "price": "2,299", "orig": "2,899", "badge": "Trending", "img": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&q=80", "is_featured": True},
    {"id": "west2", "name": "Classic Denim Jeans", "cat": "Western Wear", "sub": "Jeans", "price": "1,499", "orig": "1,999", "badge": "", "img": "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=500&q=80", "is_featured": False},
    {"id": "west3", "name": "Satin Silk Top", "cat": "Western Wear", "sub": "Tops", "price": "1,199", "orig": "1,599", "badge": "New", "img": "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=500&q=80", "is_featured": False},
    
    # Accessories (3)
    {"id": "acc1", "name": "Leather Handbag", "cat": "Accessories", "sub": "Bags & Purses", "price": "2,499", "orig": "3,200", "badge": "Premium", "img": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=500&q=80", "is_featured": True},
    {"id": "acc2", "name": "Gold Plated Earrings", "cat": "Accessories", "sub": "Jewellery", "price": "899", "orig": "1,200", "badge": "New", "img": "https://images.unsplash.com/photo-1617019114583-affb34d1b3cd?w=500&q=80", "is_featured": False},
    {"id": "acc3", "name": "Silk Floral Scarf", "cat": "Accessories", "sub": "Scarves", "price": "599", "orig": "799", "badge": "", "img": "https://images.unsplash.com/photo-1583196311087-474f2615642a?w=500&q=80", "is_featured": False},
]

with app.app_context():
    # Force recreation of the Postgres schema
    db.drop_all()
    db.create_all()
    
    cat_map = {}
    subcat_map = {}
    for c in categories_data:
        cat = Category(name=c['name'], img=c['img'], bg=c['bg'])
        db.session.add(cat)
        db.session.flush() # Get ID
        cat_map[c['name']] = cat
        
        for sc_name in c['subcategories']:
            subcat = SubCategory(name=sc_name, category_id=cat.id)
            db.session.add(subcat)
            db.session.flush()
            subcat_map[f"{c['name']}:{sc_name}"] = subcat
    
    db.session.commit()
    
    # Add Products
    for p in all_products:
        category = cat_map.get(p['cat'])
        subcategory = subcat_map.get(f"{p['cat']}:{p['sub']}")
        product = Product(
            id=p['id'],
            name=p['name'],
            cat_name=p['cat'],
            category_id=category.id if category else None,
            sub_category_id=subcategory.id if subcategory else None,
            price=f"₹{p['price']}",
            orig=f"₹{p['orig']}",
            badge=p['badge'],
            img=p['img'],
            is_featured=p.get('is_featured', False),
            sizes="S, M, L, XL",
            size_chart="https://www.sizeguide.net/wp-content/uploads/2014/11/women-clothing-size-chart.jpg"
        )
        db.session.add(product)
    
    db.session.commit()
    print("Database structure updated with 9+ demo products!")
