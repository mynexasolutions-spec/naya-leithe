from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Address, Order
from extensions import oauth

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/google/login')
def google_login():
    redirect_uri = url_for('auth.google_authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/google/authorize')
def google_authorize():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        email = user_info.get('email')
        user = User.query.filter_by(email=email).first()
        if not user:
            # Create a new user if it doesn't exist
            user = User(email=email, username=user_info.get('name'))
            # Google users don't have a password initially, they login via Google
            db.session.add(user)
            db.session.commit()
        
        session['user_id'] = user.id
        session['is_admin'] = user.is_admin
        flash(f'Successfully logged in as {email}', 'success')
        return redirect(url_for('public.home'))
    
    flash('Google authentication failed', 'error')
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('public.home'))
        else:
            flash('Invalid email or password', 'error')
    return render_template('auth.html')

@auth_bp.route('/signup', methods=['POST'])
def signup():
    email = request.form.get('email')
    password = request.form.get('password')
    if User.query.filter_by(email=email).first():
        flash('Email already exists', 'error')
        return redirect(url_for('auth.login'))
    
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session['user_id'] = user.id
    return redirect(url_for('public.home'))

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    return redirect(url_for('public.home'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.phone = request.form.get('phone')
        # We keep the legacy address fields updated for backward compatibility
        user.address = request.form.get('address')
        user.city = request.form.get('city')
        user.zipcode = request.form.get('zipcode')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.date.desc()).all()
    from models import Address
    addresses = Address.query.filter_by(user_id=user.id).order_by(Address.is_default.desc()).all()
    return render_template('profile.html', user=user, orders=orders, addresses=addresses)

@auth_bp.route('/add-address', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    from models import Address
    
    is_default_checked = request.form.get('is_default') == 'on'
    is_first = Address.query.filter_by(user_id=session['user_id']).count() == 0
    
    make_default = is_default_checked or is_first
    
    if make_default:
        Address.query.filter_by(user_id=session['user_id']).update({'is_default': False})
    
    new_address = Address(
        user_id=session['user_id'],
        label=request.form.get('label'),
        full_name=request.form.get('full_name'),
        phone=request.form.get('phone'),
        address_line_1=request.form.get('address_line_1'),
        address_line_2=request.form.get('address_line_2'),
        city=request.form.get('city'),
        state=request.form.get('state'),
        pincode=request.form.get('pincode'),
        country=request.form.get('country') or 'India',
        is_default=make_default
    )
    db.session.add(new_address)
    db.session.commit()
    flash('Address added successfully!', 'success')
    return redirect(url_for('auth.profile'))

@auth_bp.route('/delete-address/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'})
        
    from models import Address
    addr = db.session.get(Address, address_id)
    if addr and addr.user_id == session['user_id']:
        db.session.delete(addr)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Address not found'})

@auth_bp.route('/set-default-address/<int:address_id>', methods=['POST'])
def set_default_address(address_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'})
        
    from models import Address
    # Remove default from all
    Address.query.filter_by(user_id=session['user_id']).update({'is_default': False})
    
    # Set new default
    addr = db.session.get(Address, address_id)
    if addr and addr.user_id == session['user_id']:
        addr.is_default = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Address not found'})

@auth_bp.route('/cancel-order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'})
        
    from models import Order
    order = db.session.get(Order, order_id)
    if not order or order.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Order not found'})
        
    if order.status.lower() not in ['pending', 'processing', 'pending payment']:
        return jsonify({'success': False, 'message': 'Order cannot be cancelled at this stage'})
        
    data = request.get_json()
    reason = data.get('reason', 'Cancelled by customer')
    
    order.status = 'Cancelled'
    order.cancel_reason = reason
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Order cancelled successfully'})

@auth_bp.route('/get-order-details/<int:order_id>')
def get_order_details(order_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'})
        
    from models import Order
    order = db.session.get(Order, order_id)
    if not order or order.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Order not found'})
        
    items = []
    for item in order.items:
        items.append({
            'name': item.product.name,
            'qty': item.quantity,
            'price': item.price_at_time,
            'img': item.product.img,
            'variation': item.variation_details
        })
        
    return jsonify({
        'success': True,
        'order_number': order.order_number,
        'status': order.status,
        'total': order.total_amount,
        'date': order.date.strftime('%b %d, %Y'),
        'items': items,
        'address': order.shipping_address
    })
