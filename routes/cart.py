from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for
from models import Product

cart_bp = Blueprint('cart', __name__)

def safe_price(price_str):
    """Safely parse price string like '₹1,299' → 1299. Returns 0 on failure."""
    try:
        return int(str(price_str).replace('₹', '').replace(',', '').strip())
    except (ValueError, AttributeError):
        return 0

@cart_bp.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0
    for product_id, quantity in cart.items():
        # Cart key may be "pid_size_color" — always look up by base ID
        base_id = product_id.split('_')[0]
        product = Product.query.get(base_id)
        if product:
            price_val = safe_price(product.price)
            item_total = price_val * quantity
            subtotal += item_total

            # Extract variation info if stored in key (format: pid_size_color)
            size, color = None, None
            if '_' in product_id:
                parts = product_id.split('_')
                if len(parts) >= 3:
                    size = parts[1] if parts[1] != 'NA' else None
                    color = parts[2] if parts[2] != 'NA' else None

            cart_items.append({
                'id': product_id,
                'product': product,
                'quantity': quantity,
                'item_total': f"₹{item_total:,}",
                'size': size,
                'color': color
            })
    return render_template('cart.html', cart_items=cart_items, subtotal=f"₹{subtotal:,}")


@cart_bp.route('/add-to-cart/<id>', methods=['POST'])
def add_to_cart(id):
    product = Product.query.get(id)
    if not product:
        # Fallback for variation keys if not found directly
        base_id = id.split('_')[0]
        product = Product.query.get(base_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
            
    size = request.form.get('size')
    color = request.form.get('color')
    
    # Create a unique key for the cart
    cart_key = id
    if size or color:
        cart_key = f"{id}_{size or 'NA'}_{color or 'NA'}"
        
    cart = session.get('cart', {})
    cart[cart_key] = cart.get(cart_key, 0) + 1
    session['cart'] = cart
    session.modified = True
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'cart_count': sum(cart.values())})
    return redirect(request.referrer or url_for('public.home'))

@cart_bp.route('/update-cart/<id>', methods=['POST'])
def update_cart(id):
    if request.is_json:
        data = request.get_json()
        quantity = int(data.get('quantity', 1))
    else:
        quantity = int(request.form.get('quantity', 1))
    cart = session.get('cart', {})
    if quantity > 0:
        cart[id] = quantity
    else:
        cart.pop(id, None)
    session['cart'] = cart
    session.modified = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        # Resolve product from key
        base_id = id.split('_')[0]
        product = Product.query.get(base_id)

        price_val = safe_price(product.price) if product else 0
        item_total = price_val * quantity

        total = 0
        for pid, qty in cart.items():
            base_pid = pid.split('_')[0]
            p = Product.query.get(base_pid)
            if p:
                total += safe_price(p.price) * qty
        return jsonify({
            'success': True, 
            'cart_count': sum(cart.values()),
            'item_total': f"₹{item_total:,}",
            'subtotal': f"₹{total:,}"
        })
    return redirect(url_for('cart.view_cart'))

@cart_bp.route('/remove-from-cart/<id>')
def remove_from_cart(id):
    cart = session.get('cart', {})
    cart.pop(id, None)
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('cart.view_cart'))
