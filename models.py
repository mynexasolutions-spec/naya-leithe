from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Profile Details
    username = db.Column(db.String(80))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    zipcode = db.Column(db.String(10))
    
    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    img = db.Column(db.String(255))
    bg = db.Column(db.String(20))
    count = db.Column(db.String(50))
    products = db.relationship('Product', backref='category', lazy=True)
    subcategories = db.relationship('SubCategory', backref='category', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Category {self.name}>"

class Product(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    cat_name = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    sub_category_id = db.Column(db.Integer, db.ForeignKey('sub_category.id'), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brand.id'), nullable=True)
    price = db.Column(db.String(20), nullable=False)
    orig = db.Column(db.String(20))
    badge = db.Column(db.String(50))
    img = db.Column(db.String(512), nullable=False)
    desc = db.Column(db.Text)
    sizes = db.Column(db.String(100))
    colors = db.Column(db.String(100))
    size_chart = db.Column(db.String(512))
    product_type = db.Column(db.String(20), default='simple') # 'simple' or 'variable'
    stock_status = db.Column(db.String(20), default='instock') # 'instock' or 'outofstock'
    is_featured = db.Column(db.Boolean, default=False)
    
    variations = db.relationship('ProductVariation', backref='product', lazy=True, cascade="all, delete-orphan")
    attributes = db.relationship('ProductAttribute', backref='product', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Product {self.name}>"

class SubCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    products = db.relationship('Product', backref='subcategory', lazy=True)

    def __repr__(self):
        return f"<SubCategory {self.name}>"

class ProductVariation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), db.ForeignKey('product.id'), nullable=False)
    price = db.Column(db.String(20))
    stock_status = db.Column(db.String(20), default='instock')

    def __repr__(self):
        return f"<Variation for {self.product_id}>"


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), default='Pending')
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.String(50), db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_time = db.Column(db.String(20), nullable=False)
    product = db.relationship('Product')

class AppConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

class Attribute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    type = db.Column(db.String(50), default='select') # 'text', 'select', 'color'

    def __repr__(self):
        return f"<Attribute {self.name}>"


class AttributeValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('attribute.id'), nullable=False)
    value = db.Column(db.String(100), nullable=False)
    attribute = db.relationship('Attribute', backref=db.backref('values', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<AttributeValue {self.value} for {self.attribute.name}>"

class ProductAttribute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), db.ForeignKey('product.id'), nullable=False)
    attribute_id = db.Column(db.Integer, db.ForeignKey('attribute.id'), nullable=False)
    attribute = db.relationship('Attribute')

class VariationOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    variation_id = db.Column(db.Integer, db.ForeignKey('product_variation.id'), nullable=False)
    attribute_value_id = db.Column(db.Integer, db.ForeignKey('attribute_value.id'), nullable=False)
    variation = db.relationship('ProductVariation', backref=db.backref('options', lazy=True, cascade="all, delete-orphan"))
    attribute_value = db.relationship('AttributeValue')

class Brand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    logo = db.Column(db.String(512))
    products = db.relationship('Product', backref='brand', lazy=True)

    def __repr__(self):
        return f"<Brand {self.name}>"

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), db.ForeignKey('product.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    customer_name = db.Column(db.String(100))
    customer_location = db.Column(db.String(100))
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Approved')
    is_featured = db.Column(db.Boolean, default=False)
    product = db.relationship('Product', backref=db.backref('reviews', lazy=True))
    user_rel = db.relationship('User', backref=db.backref('reviews', lazy=True))

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'flat', 'percentage'
    discount = db.Column(db.Float, nullable=False)
    threshold = db.Column(db.Float, default=0.0)
    usage_limit = db.Column(db.Integer, default=1)
    expiry_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

