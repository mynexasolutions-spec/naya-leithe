import os
from flask import Flask
from models import db, Category, Product, SubCategory

app = Flask(__name__)
db_path = os.path.join(app.instance_path, 'site.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Updated Categories Data
categories_data = [
    { "name": "Western Wear", "img": "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=800&q=80", "bg": "#f8e1e7", "subcategories": ["Jeans", "Tops", "Dresses", "Cord Sets"] },
    { "name": "Ethnic Wear", "img": "https://images.unsplash.com/photo-1610030469668-301755255018?w=800&q=80", "bg": "#fdf0d5", "subcategories": ["Suits", "Cotton 2-Piece Sets", "Lehenga Choli", "Blouses"] },
    { "name": "Sarees", "img": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=800&q=80", "bg": "#f2cc8f", "subcategories": ["Silk Sarees", "Cotton Sarees", "Party Wear"] },
]

new_arrivals = [
    {"id": "na1", "name": "Emerald Silk Saree", "cat": "Sarees", "sub": "Silk Sarees", "price": "₹3,499", "orig": "₹4,200", "badge": "New", "img": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=500&q=80", "is_featured": True},
    {"id": "na2", "name": "Floral Gown Set", "cat": "Western Wear", "sub": "Dresses", "price": "₹2,299", "orig": "₹2,899", "badge": "Trending", "img": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&q=80", "is_featured": True},
    {"id": "na3", "name": "Midnight Suit Set", "cat": "Ethnic Wear", "sub": "Suits", "price": "₹1,999", "orig": "₹2,400", "badge": "New", "img": "https://images.unsplash.com/photo-1610030469668-301755255018?w=500&q=80", "is_featured": True},
]

with app.app_context():
    # Clear existing data to re-seed properly
    db.drop_all()
    db.create_all()
    
    # Add Categories and Subcategories
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
    for p in new_arrivals:
        category = cat_map.get(p['cat'])
        subcategory = subcat_map.get(f"{p['cat']}:{p['sub']}")
        product = Product(
            id=p['id'],
            name=p['name'],
            cat_name=p['cat'],
            category_id=category.id if category else None,
            sub_category_id=subcategory.id if subcategory else None,
            price=p['price'],
            orig=p['orig'],
            badge=p['badge'],
            img=p['img'],
            is_featured=p.get('is_featured', False),
            sizes="S, M, L, XL",
            size_chart="https://www.sizeguide.net/wp-content/uploads/2014/11/women-clothing-size-chart.jpg"
        )
        db.session.add(product)
    
    db.session.commit()
    print(f"Local SQLite database seeded successfully in {db_path}!")
