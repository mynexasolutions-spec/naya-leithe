from flask import Blueprint, render_template, request, abort, session, jsonify
from models import db, Category, Product, SubCategory, Review, User
from routes.admin import slugify

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def home():
    categories = Category.query.all()
    all_products = Product.query.all()
    
    # Expand products for display (showing each color variation)
    expanded_products = []
    for p in all_products:
        if p.product_type == 'variable' and p.variations:
            # Group by color
            color_variations = {}
            for v in p.variations:
                color_opt = next((opt for opt in v.options if 'color' in opt.attribute_value.attribute.name.lower()), None)
                color_id = color_opt.attribute_value_id if color_opt else 'none'
                if color_id not in color_variations:
                    color_variations[color_id] = v
            
            for color_id, var in color_variations.items():
                expanded_products.append({'product': p, 'variation': var})
        else:
            expanded_products.append({'product': p, 'variation': None})

    new_arrivals = [p for p in expanded_products if p['product'].badge == 'New'][:8]
    featured_products = [p for p in expanded_products if p['product'].is_featured][:8]
    
    category_sections = []
    for cat in categories:
        prods = [p for p in expanded_products if p['product'].cat_name == cat.name][:8]
        if prods:
            category_sections.append({
                'name': cat.name,
                'products': prods,
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
    if selected_categories:
        query = query.join(Category).filter(Category.name.in_(selected_categories))
    
    if selected_subcategories:
        query = query.join(SubCategory).filter(SubCategory.name.in_(selected_subcategories))

    on_sale = request.args.get('on_sale')
    if on_sale:
        query = query.filter(Product.orig != None, Product.orig != '')
        
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
        
    related = Product.query.filter(Product.cat_name == product.cat_name, Product.id != product.id).limit(4).all()
    
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
