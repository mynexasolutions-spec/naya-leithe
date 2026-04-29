from app import app
from models import db, Attribute, Product, ProductAttribute, ProductVariation

with app.app_context():
    print("--- ATTRIBUTES ---")
    for a in Attribute.query.all():
        print(f"ID: {a.id}, Name: {a.name}, Slug: {a.slug}")
    
    print("\n--- PRODUCT LINKS ---")
    for pa in ProductAttribute.query.all():
        print(f"Product: {pa.product_id}, Attribute: {pa.attribute_id}")
    
    print("\n--- VARIATIONS ---")
    for v in ProductVariation.query.all():
        print(f"ID: {v.id}, Product: {v.product_id}, Price: {v.price}")
