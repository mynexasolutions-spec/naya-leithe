from flask import Blueprint, render_template, request, abort, session, jsonify
from models import db, Category, Product, SubCategory, Review, User
from routes.admin import slugify
from extensions import cache
from sqlalchemy.orm import selectinload

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
@cache.cached(timeout=300, query_string=True)
def home():
    categories = Category.query.all()
    
    new_products = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes),
        selectinload(Product.images)
    ).filter_by(is_new_arrival=True).order_by(Product.id.desc()).limit(12).all()
    new_arrivals = []
    for p in new_products:
        new_arrivals.append({'product': p, 'variation': None})
        
    featured_raw = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes),
        selectinload(Product.images)
    ).filter_by(is_featured=True).limit(12).all()
    featured_products = []
    for p in featured_raw:
        featured_products.append({'product': p, 'variation': None})
    
    all_cat_names = [cat.name for cat in categories]
    all_cat_products = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes),
        selectinload(Product.images)
    ).filter(Product.cat_name.in_(all_cat_names)).limit(100).all()
    
    cat_products_map = {}
    for p in all_cat_products:
        if p.cat_name not in cat_products_map:
            cat_products_map[p.cat_name] = []
        if len(cat_products_map[p.cat_name]) < 8:
            cat_products_map[p.cat_name].append(p)
    
    category_sections = []
    for cat in categories:
        prods = cat_products_map.get(cat.name, [])
        if prods:
            section_prods = [{'product': p, 'variation': None} for p in prods]
            category_sections.append({
                'name': cat.name,
                'products': section_prods,
                'id': slugify(cat.name)
            })
    
    featured_reviews = Review.query.filter_by(is_featured=True, status='Approved').all()
    
    return render_template('index.html', 
                           new_arrivals=new_arrivals, 
                           category_sections=category_sections, 
                           categories=categories,
                           featured_products=featured_products,
                           featured_reviews=featured_reviews)

@public_bp.route('/shop')
def shop():
    selected_categories = request.args.getlist('category')
    selected_subcategories = request.args.getlist('subcategory')
    
    query = Product.query
    
    # Text Search
    search_query = request.args.get('search', '').strip()
    if search_query:
        query = query.filter(Product.name.ilike(f"%{search_query}%") | Product.desc.ilike(f"%{search_query}%"))
        
    if selected_categories:
        query = query.join(Category).filter(Category.name.in_(selected_categories))
    
    if selected_subcategories:
        query = query.join(SubCategory).filter(SubCategory.name.in_(selected_subcategories))

    on_sale = request.args.get('on_sale')
    if on_sale:
        query = query.filter(Product.orig != None, Product.orig != '')

    # Price max filtering
    from sqlalchemy import func, cast, Numeric
    clean_price = func.replace(func.replace(Product.price, '₹', ''), ',', '')
    
    price_max = request.args.get('price_max', type=float)
    if price_max is not None and price_max < 10000:
        query = query.filter(cast(clean_price, Numeric) <= price_max)
        
    # Sorting
    sort_by = request.args.get('sort_by', 'newest')
    if sort_by == 'price_asc':
        query = query.order_by(cast(clean_price, Numeric).asc())
    elif sort_by == 'price_desc':
        query = query.order_by(cast(clean_price, Numeric).desc())
    elif sort_by == 'popularity':
        from models import Review
        review_count = db.session.query(
            Review.product_id, 
            func.count(Review.id).label('review_count')
        ).filter(Review.status == 'Approved').group_by(Review.product_id).subquery()
        
        query = query.outerjoin(review_count, Product.id == review_count.c.product_id).order_by(
            func.coalesce(review_count.c.review_count, 0).desc()
        )
    else: # newest
        query = query.order_by(Product.id.desc())
        
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    categories = Category.query.all()
    
    return render_template('shop.html', 
                           products=products, 
                           pagination=pagination,
                           active_categories=selected_categories, 
                           all_categories=categories, 
                           active_subcategories=selected_subcategories)

@public_bp.route('/product/<id>')
def product_detail(id):
    product = db.session.get(Product, id)
    if not product:
        abort(404)
    
    variation_id = request.args.get('v')
    selected_variation = None
    if variation_id:
        from models import ProductVariation
        selected_variation = db.session.get(ProductVariation, variation_id)
        
    related = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes),
        selectinload(Product.images)
    ).filter(Product.cat_name == product.cat_name, Product.id != product.id).limit(4).all()
    
    # Get approved reviews for this product
    from models import Review
    approved_reviews = Review.query.filter_by(product_id=id, status='Approved').order_by(Review.date.desc()).all()
    
    return render_template('product.html', 
                           product=product, 
                           related=related, 
                           selected_variation=selected_variation,
                           reviews=approved_reviews)

@public_bp.route('/add-review/<product_id>', methods=['POST'])
def add_review(product_id):
    from models import db, Review, User
    
    name = request.form.get('name')
    rating = request.form.get('rating')
    comment = request.form.get('comment')
    
    if not rating or not comment:
        return jsonify({'success': False, 'message': 'Rating and comment are required.'}), 400
        
    user_id = session.get('user_id')
    if not name and user_id:
        user = db.session.get(User, user_id)
        if user:
            name = user.username or user.email.split('@')[0]
            
    if not name:
        name = "Anonymous"
        
    new_review = Review(
        product_id=product_id,
        user_id=user_id,
        customer_name=name,
        rating=int(rating),
        comment=comment,
        status='Pending'
    )
    
    db.session.add(new_review)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': 'Your review has been submitted and is awaiting approval.'
    })
@public_bp.route('/wishlist')
def wishlist():
    wishlist_ids = session.get('wishlist', [])
    products = Product.query.filter(Product.id.in_(wishlist_ids)).all()
    return render_template('wishlist.html', products=products)

@public_bp.route('/blogs')
def blogs():
    return render_template('blog.html')

@public_bp.route('/about')
def about():
    return render_template('about.html')

@public_bp.route('/privacy-policy')
def privacy():
    return render_template('privacy.html')

@public_bp.route('/terms-conditions')
def terms():
    return render_template('terms.html')

@public_bp.route('/shipping-policy')
def shipping():
    return render_template('shipping.html')

@public_bp.route('/cancellation-refund')
def refund():
    return render_template('refund.html')

@public_bp.route('/contact')
def contact():
    return render_template('contact.html')

@public_bp.route('/toggle-wishlist/<id>', methods=['POST'])
def toggle_wishlist(id):
    wishlist = session.get('wishlist', [])
    if id in wishlist:
        wishlist.remove(id)
        action = 'removed'
    else:
        wishlist.append(id)
        action = 'added'
    session['wishlist'] = wishlist
    session.modified = True
    return jsonify({'success': True, 'action': action, 'wishlist_count': len(wishlist)})
