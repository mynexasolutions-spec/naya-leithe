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
    from models import ProductVariation
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0
    for product_id, quantity in cart.items():
        # Key format: "var:ID" for new variations, or legacy "pid_size_color"
        product = None
        variation = None
        size, color = None, None
        display_price = 0

        if product_id.startswith('var:'):
            var_id = product_id.split(':')[1]
            variation = ProductVariation.query.get(var_id)
            if variation:
                product = variation.product
                display_price = safe_price(variation.price)
                # Extract options
                for opt in variation.options:
                    attr_name = opt.attribute_value.attribute.name.lower()
                    if 'size' in attr_name: size = opt.attribute_value.value
                    if 'color' in attr_name: color = opt.attribute_value.value
        else:
            # Legacy or Simple Product
            base_id = product_id.split('_')[0]
            product = Product.query.get(base_id)
            if product:
                display_price = safe_price(product.price)
                if '_' in product_id:
                    parts = product_id.split('_')
                    if len(parts) >= 3:
                        size = parts[1] if parts[1] != 'NA' else None
                        color = parts[2] if parts[2] != 'NA' else None

        if product:
            item_total = display_price * quantity
            subtotal += item_total

            # Find variation image if color exists
            var_img = None
            if variation:
                color_opt = next((opt for opt in variation.options if 'color' in opt.attribute_value.attribute.name.lower()), None)
                if color_opt:
                    for p_img in product.images:
                        if p_img.attribute_value_id == color_opt.attribute_value_id:
                            var_img = p_img.img_url
                            break

            cart_items.append({
                'id': product_id,
                'product': product,
                'variation': variation,
                'quantity': quantity,
                'item_total': f"₹{item_total:,}",
                'display_price': f"₹{display_price:,}",
                'var_img': var_img,
                'size': size,
                'color': color
            })
    return render_template('cart.html', cart_items=cart_items, subtotal=f"₹{subtotal:,}")


@cart_bp.route('/add-to-cart/<id>', methods=['POST'])
def add_to_cart(id):
    variation_id = request.form.get('variation_id')
    
    # Use "var:ID" as cart key for distinct variation tracking
    if variation_id:
        cart_key = f"var:{variation_id}"
    else:
        # Fallback for simple products
        size = request.form.get('size')
        color = request.form.get('color')
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
        # Resolve product/price from key
        from models import ProductVariation
        display_price = 0
        if id.startswith('var:'):
            var_id = id.split(':')[1]
            var = ProductVariation.query.get(var_id)
            if var: display_price = safe_price(var.price)
        else:
            base_id = id.split('_')[0]
            product = Product.query.get(base_id)
            if product: display_price = safe_price(product.price)

        item_total = display_price * quantity

        total = 0
        for pid, qty in cart.items():
            if pid.startswith('var:'):
                v_id = pid.split(':')[1]
                v = ProductVariation.query.get(v_id)
                if v: total += safe_price(v.price) * qty
            else:
                base_pid = pid.split('_')[0]
                p = Product.query.get(base_pid)
                if p: total += safe_price(p.price) * qty

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
