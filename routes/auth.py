from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User, Order

auth_bp = Blueprint('auth', __name__)

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
    
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.phone = request.form.get('phone')
        user.address = request.form.get('address')
        user.city = request.form.get('city')
        user.zipcode = request.form.get('zipcode')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.date.desc()).all()
    return render_template('profile.html', user=user, orders=orders)
