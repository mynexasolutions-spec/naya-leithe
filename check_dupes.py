from app import app, db
from models import Category, Product
from sqlalchemy import func

with app.app_context():
    # Check for duplicate category names
    cat_dupes = db.session.query(Category.name, func.count(Category.id)).group_by(Category.name).having(func.count(Category.id) > 1).all()
    print("--- CATEGORY DUPLICATES (Same Name) ---")
    if cat_dupes:
        for name, count in cat_dupes:
            print(f"Name: '{name}' appears {count} times")
    else:
        print("No duplicate category names found.")

    # Check for duplicate product names
    prod_dupes = db.session.query(Product.name, func.count(Product.id)).group_by(Product.name).having(func.count(Product.id) > 1).all()
    print("\n--- PRODUCT DUPLICATES (Same Name) ---")
    if prod_dupes:
        for name, count in prod_dupes:
            print(f"Name: '{name}' appears {count} times")
    else:
        print("No duplicate product names found.")

    # List all categories just to be safe
    all_cats = Category.query.all()
    print("\n--- ALL CATEGORIES IN DB ---")
    for c in all_cats:
        print(f"ID: {c.id}, Name: {c.name}")
