from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash
from models import db, Product, Category, SubCategory, ProductVariation, User, Address, Order, OrderItem

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
        options = []
        display_price = 0

        if product_id.startswith('var:'):
            var_id = product_id.split(':')[1]
            variation = db.session.get(ProductVariation, var_id)
            if variation:
                product = variation.product
                display_price = safe_price(variation.price)
                # Extract options
                for opt in variation.options:
                    attr_name = opt.attribute_value.attribute.name.lower()
                    options.append({'name': opt.attribute_value.attribute.name, 'value': opt.attribute_value.value})
                    if 'size' in attr_name: size = opt.attribute_value.value
                    if 'color' in attr_name: color = opt.attribute_value.value
        else:
            # Legacy or Simple Product
            base_id = product_id.split('_')[0]
            product = db.session.get(Product, base_id)
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
                'color': color,
                'options': options
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
            var = db.session.get(ProductVariation, var_id)
            if var: display_price = safe_price(var.price)
        else:
            base_id = id.split('_')[0]
            product = db.session.get(Product, base_id)
            if product: display_price = safe_price(product.price)

        item_total = display_price * quantity

        total = 0
        for pid, qty in cart.items():
            if pid.startswith('var:'):
                v_id = pid.split(':')[1]
                v = db.session.get(ProductVariation, v_id)
                if v: total += safe_price(v.price) * qty
            else:
                base_pid = pid.split('_')[0]
                p = db.session.get(Product, base_pid)
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

@cart_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please login to proceed to checkout', 'info')
        return redirect(url_for('auth.login'))
        
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('public.shop'))
        
    if request.method == 'POST':
        # This route is now just for GET rendering. 
        # Form submission is handled via AJAX to /place-order
        pass
        
    # Calculate cart total and fetch items
    from models import ProductVariation, Product, User
    total = 0
    cart_items = []
    for pid, qty in cart.items():
        if pid.startswith('var:'):
            v = db.session.get(ProductVariation, pid.split(':')[1])
            if v: 
                price = float(v.price.replace('₹', '').replace(',', '').strip() if v.price else 0)
                total += price * qty
                # Get variation details (Color, Size etc)
                details = []
                for opt in v.options:
                    details.append(f"{opt.attribute_value.value}")
                details_str = f" ({', '.join(details)})" if details else ""
                cart_items.append({'name': f"{v.product.name}{details_str}", 'price': price, 'qty': qty, 'image': v.img_url})
        else:
            p = db.session.get(Product, pid.split('_')[0])
            if p: 
                price = float(p.price.replace('₹', '').replace(',', '').strip() if p.price else 0)
                total += price * qty
                cart_items.append({'name': p.name, 'price': price, 'qty': qty, 'image': p.img})
            
    user = db.session.get(User, session['user_id'])
    
    # Fetch Payment Settings
    from models import AppConfig, Address
    def get_config(k, default=None):
        c = AppConfig.query.filter_by(key=k).first()
        return c.value if c else default

    online_payment = get_config('online_payment_enabled') == 'true'
    partial_payment = get_config('partial_payment_enabled') == 'true'
    razorpay_key_id = get_config('razorpay_key_id')
    
    addresses = Address.query.filter_by(user_id=session['user_id']).order_by(Address.is_default.desc()).all()
    
    return render_template('checkout.html', user=user, total=total, cart_items=cart_items,
                           online_payment=online_payment, 
                           partial_payment=partial_payment,
                           razorpay_key_id=razorpay_key_id,
                           addresses=addresses)

import razorpay
import uuid
from datetime import datetime

@cart_bp.route('/place-order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
        
    cart = session.get('cart', {})
    if not cart:
        return jsonify({'success': False, 'message': 'Cart is empty'})

    data = request.json
    payment_method = data.get('payment_method', 'COD')
    
    # Calculate Total
    from models import Product, Category, SubCategory, ProductVariation, User, Address, Order, OrderItem, AppConfig
    total = 0
    items_to_add = []
    
    for pid, qty in cart.items():
        if pid.startswith('var:'):
            v_id = pid.split(':')[1]
            v = db.session.get(ProductVariation, v_id)
            if v: 
                price = float(v.price.replace('₹', '').replace(',', '').strip() if v.price else 0)
                total += price * qty
                items_to_add.append({'product_id': v.product_id, 'variation_id': v.id, 'qty': qty, 'price': price})
        else:
            p_id = pid.split('_')[0]
            p = db.session.get(Product, p_id)
            if p: 
                price = float(p.price.replace('₹', '').replace(',', '').strip() if p.price else 0)
                total += price * qty
                items_to_add.append({'product_id': p.id, 'variation_id': None, 'qty': qty, 'price': price})

    order_number = f"ORD-{int(datetime.now().timestamp())}-{str(uuid.uuid4())[:4].upper()}"
    
    # Process Address
    from models import Address
    address_id = data.get('address_id')
    shipping_addr_str = ""
    
    if address_id == 'new':
        full_name = data.get('full_name', '')
        phone = data.get('phone', '')
        addr1 = data.get('address_line_1', '')
        addr2 = data.get('address_line_2', '')
        city = data.get('city', '')
        state = data.get('state', '')
        pincode = data.get('pincode', '')
        country = data.get('country', 'India')
        label = data.get('label', '')
        
        addr2_str = f"{addr2}\n" if addr2 else ""
        shipping_addr_str = f"{full_name}\n{addr1}\n{addr2_str}{city}, {state} {pincode}\n{country}\nPhone: {phone}"
        
        if data.get('save_address'):
            is_first = Address.query.filter_by(user_id=session['user_id']).count() == 0
            new_addr = Address(
                user_id=session['user_id'],
                label=label,
                full_name=full_name,
                phone=phone,
                address_line_1=addr1,
                address_line_2=addr2,
                city=city,
                state=state,
                pincode=pincode,
                country=country,
                is_default=is_first
            )
            db.session.add(new_addr)
    else:
        addr = db.session.get(Address, address_id)
        if addr and addr.user_id == session['user_id']:
            addr2_str = f"{addr.address_line_2}\n" if addr.address_line_2 else ""
            shipping_addr_str = f"{addr.full_name}\n{addr.address_line_1}\n{addr2_str}{addr.city}, {addr.state} {addr.pincode}\n{addr.country}\nPhone: {addr.phone}"
            
    new_order = Order(
        order_number=order_number,
        user_id=session['user_id'],
        total_amount=f"₹{total:,.2f}",
        payment_method=payment_method,
        status='Pending Payment' if payment_method in ['Online', 'Partial'] else 'Processing',
        payment_status='Unpaid',
        shipping_address=shipping_addr_str
    )
    db.session.add(new_order)
    db.session.flush() # get ID
    
    for item in items_to_add:
        v_details = ""
        if item['variation_id']:
            v = db.session.get(ProductVariation, item['variation_id'])
            if v:
                details_list = []
                for opt in v.options:
                    details_list.append(f"{opt.attribute.name}: {opt.value.value}")
                v_details = ", ".join(details_list)
        
        oi = OrderItem(
            order_id=new_order.id,
            product_id=item['product_id'],
            variation_id=item['variation_id'],
            quantity=item['qty'],
            price_at_time=f"₹{item['price']:,.2f}",
            variation_details=v_details
        )
        db.session.add(oi)

    if payment_method == 'COD':
        db.session.commit()
        session.pop('cart', None)
        return jsonify({'success': True, 'method': 'COD', 'redirect': url_for('auth.profile')})
        
    elif payment_method in ['Online', 'Partial']:
        # Fetch Razorpay keys
        key_id = AppConfig.query.filter_by(key='razorpay_key_id').first()
        key_secret = AppConfig.query.filter_by(key='razorpay_key_secret').first()
        
        if not key_id or not key_secret:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Payment gateway not configured properly.'})
            
        amount_to_pay = total
        if payment_method == 'Partial':
            partial_percent = AppConfig.query.filter_by(key='partial_payment_percentage').first()
            if partial_percent and partial_percent.value.isdigit():
                amount_to_pay = total * (int(partial_percent.value) / 100.0)
                
        # Initialize Razorpay Client
        client = razorpay.Client(auth=(key_id.value, key_secret.value))
        
        # Create Order in Razorpay
        try:
            rzp_order = client.order.create({
                "amount": int(amount_to_pay * 100), # Amount in paise
                "currency": "INR",
                "receipt": new_order.order_number,
                "payment_capture": "1" # Auto capture
            })
            
            new_order.razorpay_order_id = rzp_order['id']
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'method': payment_method,
                'razorpay_order_id': rzp_order['id'],
                'amount': rzp_order['amount'],
                'currency': rzp_order['currency'],
                'order_id': new_order.id
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)})

@cart_bp.route('/verify-payment', methods=['POST'])
def verify_payment():
    data = request.json
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_signature = data.get('razorpay_signature')
    order_id = data.get('order_id')
    
    from models import AppConfig, Order, db
    key_id = AppConfig.query.filter_by(key='razorpay_key_id').first()
    key_secret = AppConfig.query.filter_by(key='razorpay_key_secret').first()
    
    client = razorpay.Client(auth=(key_id.value, key_secret.value))
    
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        
        order = db.session.get(Order, order_id)
        if order:
            order.status = 'Processing'
            if order.payment_method == 'Partial':
                order.payment_status = 'Partially Paid'
            else:
                order.payment_status = 'Paid'
            order.razorpay_payment_id = razorpay_payment_id
            db.session.commit()
            session.pop('cart', None)
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Payment verification failed'})

