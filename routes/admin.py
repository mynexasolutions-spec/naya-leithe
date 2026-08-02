from flask import Blueprint, render_template, session, redirect, url_for, abort, request, flash, jsonify
from functools import wraps
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import func

def slugify(text):
    if not text:
        return str(int(datetime.now().timestamp()))
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')
from models import db, User, Product, Category, SubCategory, ProductVariation, Order, OrderItem, AppConfig, Attribute, AttributeValue, ProductAttribute, VariationOption, Brand, Review, Coupon, ProductImage
from extensions import cache
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask import current_app
import cloudinary.uploader
import re
import io
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

admin_bp = Blueprint('admin', __name__)

from flask import g

def get_current_user():
    if 'user' not in g:
        user_id = session.get('user_id')
        g.user = db.session.get(User, user_id) if user_id else None
    return g.user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        user = get_current_user()
        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def validate_csrf():
    form_token = request.form.get('csrf_token')
    session_token = session.get('csrf_token')
    if not form_token or form_token != session_token:
        user = get_current_user()
        if not (user and user.is_admin):
            abort(403, "CSRF validation failed – token missing")

def save_image(file, folder):
    if not file or not file.filename:
        return None
    # Compress image to optimize size and avoid Cloudinary size errors
    try:
        img = Image.open(file)
        # Convert RGBA to RGB for JPEG formatting
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Scale down if extremely large
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
        # Compress in-memory to JPEG
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG', quality=65, optimize=True)
        img_io.seek(0)
        
        # Upload compressed bytes to Cloudinary
        upload_result = cloudinary.uploader.upload(img_io, folder=f"naye-leithe/{folder}")
    except Exception as e:
        print(f"PIL Image compression failed, uploading original file: {e}")
        file.seek(0)
        upload_result = cloudinary.uploader.upload(file, folder=f"naye-leithe/{folder}")
        
    return upload_result.get('secure_url')

def delete_image(image_url):
    if not image_url or 'cloudinary' not in image_url:
        return
    # Extract public_id from cloudinary URL
    # Format: https://res.cloudinary.com/cloud_name/image/upload/v1234567/naye-leithe/folder/public_id.jpg
    try:
        parts = image_url.split('/')
        # The public_id is usually the path after '/upload/' (excluding the version)
        # We need to find 'upload' and take everything after the version segment
        upload_idx = -1
        for i, part in enumerate(parts):
            if part == 'upload':
                upload_idx = i
                break
        
        if upload_idx != -1:
            # Skip 'upload' and the version (e.g., 'v1234567')
            id_parts = parts[upload_idx + 2:]
            public_id_with_ext = "/".join(id_parts)
            # Remove extension
            public_id = public_id_with_ext.rsplit('.', 1)[0]
            cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print(f"Error deleting from Cloudinary: {e}")

def save_images_parallel(files, folder, max_workers=4):
    if not files:
        return []
    urls = [None] * len(files)
    def _upload(idx_file):
        idx, f = idx_file
        if f and f.filename:
            return (idx, save_image(f, folder))
        return (idx, None)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(files))) as executor:
        futures = {executor.submit(_upload, (i, f)): i for i, f in enumerate(files)}
        for future in as_completed(futures):
            idx, url = future.result()
            urls[idx] = url
    return urls

@admin_bp.route('/admin/dashboard')
@admin_required
def dashboard():
    stats = cache.get('admin_dashboard_stats')
    if not stats:
        products_count = Product.query.count()
        categories_count = Category.query.count()
        users_count = User.query.filter_by(is_admin=False).count()
        orders_count = Order.query.count()
        stats = {
            'products_count': products_count,
            'categories_count': categories_count,
            'users_count': users_count,
            'orders_count': orders_count
        }
        cache.set('admin_dashboard_stats', stats, timeout=60)
    
    recent_orders = Order.query.options(
        joinedload(Order.user),
        selectinload(Order.items)
    ).order_by(Order.id.desc()).limit(5).all()
    
    low_stock_products = Product.query.filter(Product.stock_status == 'outofstock').limit(3).all()
    if not low_stock_products:
        low_stock_products = Product.query.limit(2).all()
        
    return render_template('admin/dashboard.html', 
                           products_count=stats['products_count'],
                           categories_count=stats['categories_count'],
                           users_count=stats['users_count'],
                           orders_count=stats['orders_count'],
                           recent_orders=recent_orders,
                           low_stock_products=low_stock_products)

# --- PRODUCT ROUTES ---

@admin_bp.route('/admin/products')
@admin_required
def products():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    category_filter = request.args.get('category')
    status_filter = request.args.get('status')
    
    query = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes).joinedload(ProductAttribute.attribute),
        selectinload(Product.variations).selectinload(ProductVariation.options).joinedload(VariationOption.attribute_value)
    )
    
    if category_filter and category_filter != 'all':
        query = query.filter(Product.cat_name == category_filter)
    
    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            query = query.filter(Product.stock_status == 'instock')
        elif status_filter == 'draft':
            query = query.filter(Product.stock_status == 'outofstock')
    
    products_pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    categories = cache.get('all_categories_nav')
    if not categories:
        categories = Category.query.options(selectinload(Category.subcategories)).all()
        cache.set('all_categories_nav', categories, timeout=300)

    return render_template('admin/products.html', products=products_pagination.items, pagination=products_pagination, category_filter=category_filter, status_filter=status_filter, categories=categories)

def upload_product_images_parallel(img_file, size_chart_file, gallery_files, var_img_files_dict):
    items_to_upload = []
    
    if img_file and img_file.filename:
        items_to_upload.append(('main', 0, img_file, 'products'))
        
    if size_chart_file and size_chart_file.filename:
        items_to_upload.append(('size_chart', 0, size_chart_file, 'size_charts'))
        
    if gallery_files:
        for idx, g_file in enumerate(gallery_files):
            if g_file and g_file.filename:
                items_to_upload.append(('gallery', idx, g_file, 'products'))
                
    if var_img_files_dict:
        for v_idx, v_file in var_img_files_dict.items():
            if v_file and v_file.filename:
                items_to_upload.append(('variation', v_idx, v_file, 'products'))

    if not items_to_upload:
        return None, None, [], {}

    main_url = None
    size_chart_url = None
    gallery_urls = [None] * len(gallery_files if gallery_files else [])
    var_urls = {}

    def _worker(item):
        type_key, idx, file_obj, folder = item
        url = save_image(file_obj, folder)
        return (type_key, idx, url)

    with ThreadPoolExecutor(max_workers=min(8, len(items_to_upload))) as executor:
        futures = [executor.submit(_worker, item) for item in items_to_upload]
        for future in as_completed(futures):
            type_key, idx, url = future.result()
            if type_key == 'main':
                main_url = url
            elif type_key == 'size_chart':
                size_chart_url = url
            elif type_key == 'gallery':
                gallery_urls[idx] = url
            elif type_key == 'variation':
                var_urls[idx] = url

    gallery_urls = [u for u in gallery_urls if u]
    return main_url, size_chart_url, gallery_urls, var_urls

def save_product_attributes_and_sizes_colors(product, selected_attr_ids):
    ProductAttribute.query.filter_by(product_id=product.id).delete()
    
    sizes_list = []
    colors_list = []
    
    for attr_id in selected_attr_ids:
        try:
            attr_id_int = int(attr_id)
        except (ValueError, TypeError):
            continue
            
        prod_attr = ProductAttribute(product_id=product.id, attribute_id=attr_id_int)
        db.session.add(prod_attr)
        
        val_ids = request.form.getlist(f'attr_val_{attr_id}[]')
        if val_ids:
            attr = db.session.get(Attribute, attr_id_int)
            if attr:
                attr_name_lower = attr.name.lower()
                clean_val_ids = [int(v) for v in val_ids if str(v).isdigit()]
                if clean_val_ids:
                    val_objs = AttributeValue.query.filter(AttributeValue.id.in_(clean_val_ids)).all()
                    val_names = [v.value for v in val_objs]
                    
                    if 'size' in attr_name_lower:
                        sizes_list.extend(val_names)
                    elif 'color' in attr_name_lower:
                        colors_list.extend(val_names)

    if sizes_list:
        unique_sizes = list(dict.fromkeys(sizes_list))
        product.sizes = ", ".join(unique_sizes)
    elif request.form.get('sizes'):
        product.sizes = request.form.get('sizes')

    if colors_list:
        unique_colors = list(dict.fromkeys(colors_list))
        product.colors = ", ".join(unique_colors)
    elif request.form.get('colors'):
        product.colors = request.form.get('colors')

@admin_bp.route('/admin/product/new', methods=['GET', 'POST'])
@admin_required
def new_product():
    if request.method == 'POST':
        name = request.form.get('name')
        price_raw = request.form.get('price', '').replace('₹', '').strip()
        price = price_raw if price_raw else '0'
        orig_raw = request.form.get('orig', '').replace('₹', '').strip()
        orig = f"₹{orig_raw}" if orig_raw else None
        
        badge = request.form.get('badge')
        desc = request.form.get('desc')
        short_desc = request.form.get('short_desc')
        product_type = request.form.get('product_type', 'simple')
        stock_status = request.form.get('stock_status', 'instock')
        category_id = request.form.get('category_id') or None
        sub_category_id = request.form.get('sub_category_id') or None
        brand_id = request.form.get('brand_id') or None
        is_featured = True if request.form.get('is_featured') == 'on' else False
        is_new_arrival = True if request.form.get('is_new_arrival') == 'on' else False
        
        category = db.session.get(Category, category_id)
        cat_name = category.name if category else 'Uncategorized'
        
        # Parallel image upload
        img_file = request.files.get('img')
        size_chart_file = request.files.get('size_chart')
        gallery_files = request.files.getlist('gallery[]')
        gallery_files = [f for f in gallery_files if f and f.filename]

        v_indices = request.form.getlist('var_idx[]')
        v_stocks = request.form.getlist('var_stock[]')
        v_prices = request.form.getlist('var_price[]')
        num_variations = len(v_stocks)

        var_img_files = {}
        for i in range(num_variations):
            v_idx = v_indices[i] if i < len(v_indices) else None
            if v_idx:
                v_file = request.files.get(f'var_img_{v_idx}')
                if v_file and v_file.filename:
                    var_img_files[i] = v_file

        main_url, size_chart_url, gallery_urls, var_urls = upload_product_images_parallel(
            img_file, size_chart_file, gallery_files, var_img_files
        )
        
        new_id = slugify(name)
        base_id = new_id
        counter = 1
        while db.session.get(Product, new_id):
            new_id = f"{base_id}-{counter}"
            counter += 1
            
        try:
            product = Product(
                id=new_id, 
                name=name, 
                price=f"₹{price}", 
                orig=orig,
                cat_name=cat_name, 
                category_id=category_id,
                sub_category_id=sub_category_id,
                brand_id=brand_id,
                badge=badge, 
                img=main_url or '',
                size_chart=size_chart_url,
                desc=desc,
                short_desc=short_desc,
                product_type=product_type,
                stock_status=stock_status,
                is_featured=is_featured,
                is_new_arrival=is_new_arrival
            )
            db.session.add(product)
            db.session.flush() # Flush to get product object ready for relations
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating product: {str(e)}', 'error')
            return redirect(url_for('admin.new_product'))
        
        # Save attributes and sizes/colors
        selected_attr_ids = request.form.getlist('product_attributes[]')
        if product_type == 'variable' and not selected_attr_ids:
            flash('Variable products must have at least one attribute selected.', 'error')
            return redirect(url_for('admin.new_product'))

        save_product_attributes_and_sizes_colors(product, selected_attr_ids)
        
        # Handle Gallery Images
        for url in gallery_urls:
            if url:
                db.session.add(ProductImage(product_id=new_id, img_url=url))
        
        # Handle Variations if Variable Product
        if product_type == 'variable':
            attr_values_map = {}
            for attr_id in selected_attr_ids:
                attr_values_map[attr_id] = request.form.getlist(f'var_attr_{attr_id}[]')
            
            for i in range(num_variations):
                v_price = v_prices[i].replace('₹', '').strip() if i < len(v_prices) and v_prices[i] else price
                v_stock = v_stocks[i] if i < len(v_stocks) else 'instock'
                v_img_url = var_urls.get(i, None)

                variation = ProductVariation(
                    product_id=new_id,
                    price=f"₹{v_price}",
                    stock_status=v_stock,
                    img_url=v_img_url
                )
                db.session.add(variation)
                db.session.flush() # Get variation ID
                
                for attr_id, values_list in attr_values_map.items():
                    if i < len(values_list):
                        option = VariationOption(
                            variation_id=variation.id,
                            attribute_value_id=values_list[i]
                        )
                        db.session.add(option)

        cache.clear()
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin.products'))
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    attributes = Attribute.query.all()
    brands = Brand.query.all()
    return render_template('admin/product_form.html', categories=categories, subcategories=subcategories, attributes=attributes, brands=brands)

@admin_bp.route('/admin/product/edit/<id>', methods=['GET', 'POST'])
@admin_required
def edit_product(id):
    product = db.session.get(Product, id)
    if not product:
        abort(404)
        
    if request.method == 'POST':
        product.name = request.form.get('name')
        price = request.form.get('price').replace('₹', '').strip()
        product.price = f"₹{price}"
        orig_raw = request.form.get('orig', '').replace('₹', '').strip()
        product.orig = f"₹{orig_raw}" if orig_raw else None
        
        product.cat_name = request.form.get('cat_name')
        product.badge = request.form.get('badge')
        product.desc = request.form.get('desc')
        product.short_desc = request.form.get('short_desc')
        product.product_type = request.form.get('product_type', 'simple')
        product.stock_status = request.form.get('stock_status', 'instock')
        
        category_id = request.form.get('category_id') or None
        product.category_id = category_id
        product.sub_category_id = request.form.get('sub_category_id') or None
        product.brand_id = request.form.get('brand_id') or None
        product.is_featured = True if request.form.get('is_featured') == 'on' else False
        product.is_new_arrival = True if request.form.get('is_new_arrival') == 'on' else False
        
        category = db.session.get(Category, category_id)
        if category:
            product.cat_name = category.name
        
        # Parallel image upload
        img_file = request.files.get('img')
        size_chart_file = request.files.get('size_chart')
        gallery_files = request.files.getlist('gallery[]')
        gallery_files = [f for f in gallery_files if f and f.filename]

        v_indices = request.form.getlist('var_idx[]')
        v_stocks = request.form.getlist('var_stock[]')
        v_prices = request.form.getlist('var_price[]')
        v_existing_imgs = request.form.getlist('var_existing_img[]')
        num_variations = len(v_stocks)

        var_img_files = {}
        for i in range(num_variations):
            v_idx = v_indices[i] if i < len(v_indices) else None
            if v_idx:
                v_file = request.files.get(f'var_img_{v_idx}')
                if v_file and v_file.filename:
                    var_img_files[i] = v_file

        main_url, size_chart_url, gallery_urls, var_urls = upload_product_images_parallel(
            img_file, size_chart_file, gallery_files, var_img_files
        )
        
        if main_url:
            product.img = main_url
        if size_chart_url:
            product.size_chart = size_chart_url

        # Handle Gallery Images
        for url in gallery_urls:
            if url:
                db.session.add(ProductImage(product_id=product.id, img_url=url))
        
        # Handle removed gallery images
        remove_gallery_ids = request.form.getlist('remove_gallery[]')
        for img_id in remove_gallery_ids:
            p_img = db.session.get(ProductImage, img_id)
            if p_img:
                delete_image(p_img.img_url)
                db.session.delete(p_img)

        # Clear existing variations
        ProductVariation.query.filter_by(product_id=product.id).delete()
        
        # Save attributes and sizes/colors
        selected_attr_ids = request.form.getlist('product_attributes[]')
        save_product_attributes_and_sizes_colors(product, selected_attr_ids)
        
        # Handle Variations
        if product.product_type == 'variable':
            attr_values_map = {}
            for attr_id in selected_attr_ids:
                attr_values_map[attr_id] = request.form.getlist(f'var_attr_{attr_id}[]')
            
            for i in range(num_variations):
                v_price = v_prices[i].replace('₹', '').strip() if i < len(v_prices) and v_prices[i] else price
                v_stock = v_stocks[i] if i < len(v_stocks) else 'instock'
                
                v_img_url = v_existing_imgs[i] if i < len(v_existing_imgs) else None
                if i in var_urls:
                    v_img_url = var_urls[i]
                
                variation = ProductVariation(
                    product_id=product.id,
                    price=f"₹{v_price}",
                    stock_status=v_stock,
                    img_url=v_img_url
                )
                db.session.add(variation)
                db.session.flush() # Get variation ID
                
                for attr_id, values_list in attr_values_map.items():
                    if i < len(values_list):
                        option = VariationOption(
                            variation_id=variation.id,
                            attribute_value_id=values_list[i]
                        )
                        db.session.add(option)

        cache.clear()
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin.products'))
        
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    attributes = Attribute.query.all()
    brands = Brand.query.all()
    return render_template('admin/product_form.html', categories=categories, subcategories=subcategories, attributes=attributes, brands=brands, product=product)

@admin_bp.route('/admin/product/delete/<id>', methods=['POST'])
@admin_required
def delete_product(id):
    # CSRF Token Check (BUG-001)
    validate_csrf()
        
    product = db.session.get(Product, id)
    if product:
        # Delete from Cloudinary
        delete_image(product.img)
        delete_image(product.size_chart)
        db.session.delete(product)
        cache.clear()
        db.session.commit()
        flash('Product deleted!', 'success')
    return redirect(url_for('admin.products'))

# --- CATEGORY ROUTES ---

@admin_bp.route('/admin/categories')
@admin_required
def categories():
    all_categories = Category.query.options(selectinload(Category.subcategories)).all()
    if all_categories:
        cat_ids = [c.id for c in all_categories]
        product_counts = dict(
            db.session.query(Product.category_id, func.count(Product.id))
            .filter(Product.category_id.in_(cat_ids))
            .group_by(Product.category_id)
            .all()
        )
        for c in all_categories:
            c.product_count = product_counts.get(c.id, 0)
    return render_template('admin/categories.html', categories=all_categories)

@admin_bp.route('/admin/category/new', methods=['GET', 'POST'])
@admin_required
def new_category():
    if request.method == 'POST':
        name = request.form.get('name')
        img_file = request.files.get('img')
        img = save_image(img_file, 'categories') if img_file else None
        
        category = Category(name=name, img=img)
        db.session.add(category)
        cache.clear()
        db.session.commit()
        flash('Category added successfully!', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html')

@admin_bp.route('/admin/category/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_category(id):
    cat = db.session.get(Category, id)
    if not cat:
        abort(404)
    if request.method == 'POST':
        cat.name = request.form.get('name')
        img_file = request.files.get('img')
        if img_file and img_file.filename:
            if cat.img:
                delete_image(cat.img)
            cat.img = save_image(img_file, 'categories')
        cache.clear()
        db.session.commit()
        flash('Category updated successfully!', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', category=cat)

@admin_bp.route('/admin/category/delete/<int:id>', methods=['POST'])
@admin_required
def delete_category(id):
    # CSRF Token Check (BUG-002)
    validate_csrf()
        
    category = db.session.get(Category, id)
    if category:
        delete_image(category.img)
        db.session.delete(category)
        cache.clear()
        db.session.commit()
        flash('Category deleted!', 'success')
    return redirect(url_for('admin.categories'))

@admin_bp.route('/admin/subcategory/new', methods=['GET', 'POST'])
@admin_required
def new_subcategory():
    if request.method == 'POST':
        name = request.form.get('name')
        category_id = request.form.get('category_id')
        img_file = request.files.get('img')
        img = save_image(img_file, 'subcategories') if img_file else None
        
        subcategory = SubCategory(name=name, category_id=category_id, img=img)
        db.session.add(subcategory)
        db.session.commit()
        flash('SubCategory added successfully!', 'success')
        return redirect(url_for('admin.categories'))
    categories = Category.query.all()
    return render_template('admin/subcategory_form.html', categories=categories)

@admin_bp.route('/admin/subcategory/delete/<int:id>', methods=['POST'])
@admin_required
def delete_subcategory(id):
    # CSRF Token Check
    validate_csrf()
        
    subcategory = db.session.get(SubCategory, id)
    if subcategory:
        if subcategory.img:
            delete_image(subcategory.img)
        db.session.delete(subcategory)
        cache.clear()
        db.session.commit()
        flash('SubCategory deleted!', 'success')
        return redirect(url_for('admin.categories'))

@admin_bp.route('/admin/subcategory/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_subcategory(id):
    sub = db.session.get(SubCategory, id)
    if not sub:
        abort(404)
    if request.method == 'POST':
        sub.name = request.form.get('name')
        sub.category_id = request.form.get('category_id')
        img_file = request.files.get('img')
        if img_file and img_file.filename:
            if sub.img:
                delete_image(sub.img)
            sub.img = save_image(img_file, 'subcategories')
        db.session.commit()
        flash('SubCategory updated!', 'success')
        return redirect(url_for('admin.categories'))
    categories = Category.query.all()
    return render_template('admin/subcategory_form.html', categories=categories, subcategory=sub)

# --- CUSTOMER ROUTES ---

@admin_bp.route('/admin/customers')
@admin_required
def customers():
    page = request.args.get('page', 1, type=int)
    per_page = 30
    users_pagination = User.query.filter_by(is_admin=False).paginate(page=page, per_page=per_page, error_out=False)
    users = users_pagination.items
    if users:
        user_ids = [u.id for u in users]
        order_counts = dict(
            db.session.query(Order.user_id, func.count(Order.id))
            .filter(Order.user_id.in_(user_ids))
            .group_by(Order.user_id)
            .all()
        )
        for u in users:
            u.order_count = order_counts.get(u.id, 0)
    return render_template('admin/customers.html', users=users, pagination=users_pagination)

@admin_bp.route('/admin/customer/delete/<int:id>', methods=['POST'])
@admin_required
def delete_customer(id):
    user = db.session.get(User, id)
    if user:
        # Check if user has orders before deleting, or handle cascade
        db.session.delete(user)
        db.session.commit()
        flash('Customer removed successfully!', 'success')
    return redirect(url_for('admin.customers'))

# --- ORDER ROUTES ---

@admin_bp.route('/admin/orders')
@admin_required
def orders():
    page = request.args.get('page', 1, type=int)
    per_page = 30
    customer_id = request.args.get('customer_id')
    query = Order.query.options(joinedload(Order.user))
    if customer_id:
        query = query.filter_by(user_id=customer_id)
    orders_pagination = query.order_by(Order.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/orders.html', orders=orders_pagination.items, pagination=orders_pagination, customer_id=customer_id)

@admin_bp.route('/admin/order/<int:id>')
@admin_required
def view_order(id):
    order = Order.query.options(
        joinedload(Order.user),
        selectinload(Order.items).joinedload(OrderItem.product)
    ).filter_by(id=id).first_or_404()
    return render_template('admin/order_detail.html', order=order)

@admin_bp.route('/admin/order/update-status/<int:id>', methods=['POST'])
@admin_required
def update_order_status(id):
    order = db.session.get(Order, id)
    if order:
        new_status = request.form.get('status')
        if new_status:
            order.status = new_status
            if new_status == 'Delivered':
                order.payment_status = 'Paid'
            db.session.commit()
            flash(f'Order #{order.order_number} status updated to {new_status}!', 'success')
    return redirect(request.referrer or url_for('admin.orders'))

@admin_bp.route('/admin/order/cancel/<int:id>', methods=['POST'])
@admin_required
def admin_cancel_order(id):
    order = db.session.get(Order, id)
    if order:
        data = request.get_json()
        reason = data.get('reason', 'Cancelled by admin')
        order.status = 'Cancelled'
        order.cancel_reason = reason
        db.session.commit()
        return jsonify({'success': True, 'message': f'Order #{order.order_number} cancelled.'})
    return jsonify({'success': False, 'message': 'Order not found.'})

# --- SETTINGS ---

@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        # List all expected checkbox/boolean keys
        bool_keys = ['shipping_enabled', 'payment_method_cod', 'payment_method_online', 'partial_payment_enabled']
        
        # Handle all form data
        for key in request.form:
            value = request.form.get(key)
            config = AppConfig.query.filter_by(key=key).first()
            if config:
                config.value = value
            else:
                new_config = AppConfig(key=key, value=value)
                db.session.add(new_config)
        
        # Explicitly set booleans that were NOT in the form to 'false'
        for b_key in bool_keys:
            if b_key not in request.form:
                config = AppConfig.query.filter_by(key=b_key).first()
                if config:
                    config.value = 'false'
                else:
                    new_config = AppConfig(key=b_key, value='false')
                    db.session.add(new_config)

        cache.clear()
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('admin.settings'))
    configs = {c.key: c.value for c in AppConfig.query.all()}
    return render_template('admin/settings.html', configs=configs)

# --- ATTRIBUTE ROUTES ---

@admin_bp.route('/admin/attributes')
@admin_required
def admin_attributes():
    all_attributes = Attribute.query.options(selectinload(Attribute.values)).all()
    for attr in all_attributes:
        attr.value_count = len(attr.values)
    return render_template('admin/attributes.html', attributes=all_attributes)

@admin_bp.route('/admin/attribute/new', methods=['GET', 'POST'])
@admin_required
def admin_attribute_new():
    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug')
        image_url = request.form.get('image_url')
        attr_type = request.form.get('type', 'select')
        is_featured = True if request.form.get('is_featured') == 'on' else False
        
        if not slug:
            slug = name.lower().replace(' ', '-')
            
        attribute = Attribute(name=name, slug=slug, image_url=image_url, is_featured=is_featured, type=attr_type)
        db.session.add(attribute)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'id': attribute.id,
                'name': attribute.name,
                'slug': attribute.slug
            })
            
        flash('Attribute added successfully!', 'success')
        return redirect(url_for('admin.admin_attributes'))
    return render_template('admin/attribute_form.html')

@admin_bp.route('/admin/attribute/edit/<int:attr_id>', methods=['GET', 'POST'])
@admin_required
def admin_attribute_edit(attr_id):
    attribute = db.session.get(Attribute, attr_id)
    if not attribute:
        abort(404)
        
    if request.method == 'POST':
        attribute.name = request.form.get('name')
        attribute.slug = request.form.get('slug')
        attribute.type = request.form.get('type', 'select')
        attribute.image_url = request.form.get('image_url')
        attribute.is_featured = True if request.form.get('is_featured') == 'on' else False
        
        db.session.commit()
        flash('Attribute updated successfully!', 'success')
        return redirect(url_for('admin.admin_attributes'))
        
    return render_template('admin/attribute_form.html', attribute=attribute)

@admin_bp.route('/admin/attribute/delete/<int:attr_id>', methods=['POST'])
@admin_required
def admin_attribute_delete(attr_id):
    # CSRF Token Check
    validate_csrf()
        
    attribute = db.session.get(Attribute, attr_id)
    if attribute:
        db.session.delete(attribute)
        db.session.commit()
        flash('Attribute deleted!', 'success')
    return redirect(url_for('admin.admin_attributes'))

@admin_bp.route('/admin/attribute/<int:attr_id>/values', methods=['GET', 'POST'])
@admin_required
def admin_attribute_values(attr_id):
    attribute = db.session.get(Attribute, attr_id)
    if not attribute:
        abort(404)
        
    if request.method == 'POST':
        value_content = request.form.get('value')
        image_url = request.form.get('image_url')
        
        new_val = AttributeValue(attribute_id=attr_id, value=value_content, image_url=image_url)
        db.session.add(new_val)
        db.session.commit()
        flash('Value added!', 'success')
        return redirect(url_for('admin.admin_attribute_values', attr_id=attr_id))
        
    values = AttributeValue.query.filter_by(attribute_id=attr_id).all()
    return render_template('admin/attribute_values.html', attribute=attribute, values=values)

@admin_bp.route('/admin/attribute/value/delete/<int:val_id>', methods=['POST'])
@admin_required
def admin_attribute_value_delete(val_id):
    val = db.session.get(AttributeValue, val_id)
    if val:
        attr_id = val.attribute_id
        db.session.delete(val)
        db.session.commit()
        flash('Value removed!', 'success')
        return redirect(url_for('admin.admin_attribute_values', attr_id=attr_id))
    return redirect(url_for('admin.admin_attributes'))


@admin_bp.route('/admin/attribute/<int:attr_id>/value/quick-add', methods=['POST'])
@admin_required
def admin_attribute_value_quick_add(attr_id):
    data = request.get_json()
    value_content = data.get('value', '').strip()
    if not value_content:
        return jsonify({'success': False, 'error': 'Value is required'}), 400
    
    # Check for duplicates
    existing = AttributeValue.query.filter_by(attribute_id=attr_id).filter(AttributeValue.value.ilike(value_content)).first()
    if existing:
        return jsonify({'success': True, 'id': existing.id, 'existed': True})
    
    new_val = AttributeValue(attribute_id=attr_id, value=value_content)
    db.session.add(new_val)
    db.session.commit()
    return jsonify({'success': True, 'id': new_val.id})

# --- BRAND ROUTES ---

@admin_bp.route('/admin/brands')
@admin_required
def brands():
    all_brands = Brand.query.all()
    if all_brands:
        brand_ids = [b.id for b in all_brands]
        product_counts = dict(
            db.session.query(Product.brand_id, func.count(Product.id))
            .filter(Product.brand_id.in_(brand_ids))
            .group_by(Product.brand_id)
            .all()
        )
        for b in all_brands:
            b.product_count = product_counts.get(b.id, 0)
    return render_template('admin/brands.html', brands=all_brands)

@admin_bp.route('/admin/brand/new', methods=['GET', 'POST'])
@admin_required
def new_brand():
    if request.method == 'POST':
        name = request.form.get('name')
        logo_file = request.files.get('logo')
        logo = save_image(logo_file, 'brands') if logo_file else None
        
        brand = Brand(name=name, logo=logo)
        db.session.add(brand)
        db.session.commit()
        flash('Brand added successfully!', 'success')
        return redirect(url_for('admin.brands'))
    return render_template('admin/brand_form.html')

@admin_bp.route('/admin/brand/delete/<int:id>', methods=['POST'])
@admin_required
def delete_brand(id):
    # CSRF Token Check (BUG-003)
    validate_csrf()
        
    brand = db.session.get(Brand, id)
    if brand:
        delete_image(brand.logo)
        db.session.delete(brand)
        db.session.commit()
        flash('Brand deleted!', 'success')
    return redirect(url_for('admin.brands'))

# --- REVIEW ROUTES ---
@admin_bp.route('/admin/reviews')
@admin_required
def reviews():
    page = request.args.get('page', 1, type=int)
    per_page = 30
    reviews_pagination = Review.query.options(
        joinedload(Review.product)
    ).order_by(Review.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/reviews.html', reviews=reviews_pagination.items, pagination=reviews_pagination)

@admin_bp.route('/admin/review/new', methods=['POST'])
@admin_required
def new_review():
    customer_name = request.form.get('customer_name')
    customer_location = request.form.get('customer_location')
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment')
    is_featured = True if request.form.get('is_featured') == 'on' else False
    
    review = Review(
        customer_name=customer_name,
        customer_location=customer_location,
        rating=rating,
        comment=comment,
        is_featured=is_featured,
        status='Approved'
    )
    db.session.add(review)
    db.session.commit()
    flash('Review added successfully!', 'success')
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/admin/review/edit/<int:id>', methods=['POST'])
@admin_required
def edit_review(id):
    review = db.session.get(Review, id)
    if review:
        review.customer_name = request.form.get('customer_name')
        review.customer_location = request.form.get('customer_location')
        review.rating = int(request.form.get('rating', 5))
        review.comment = request.form.get('comment')
        review.is_featured = True if request.form.get('is_featured') == 'on' else False
        db.session.commit()
        flash('Review updated successfully!', 'success')
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/admin/review/status/<int:id>', methods=['POST'])
@admin_required
def review_status(id):
    review = db.session.get(Review, id)
    if review:
        status = request.form.get('status')
        if status in ['Approved', 'Rejected', 'Pending']:
            review.status = status
            db.session.commit()
            flash(f'Review {status.lower()} successfully!', 'success')
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/admin/review/toggle-featured/<int:id>', methods=['POST'])
@admin_required
def review_toggle_featured(id):
    review = db.session.get(Review, id)
    if review:
        review.is_featured = not review.is_featured
        db.session.commit()
        state = "featured" if review.is_featured else "unfeatured"
        flash(f'Review marked as {state}!', 'success')
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/admin/review/delete/<int:id>', methods=['POST'])
@admin_required
def delete_review(id):
    review = db.session.get(Review, id)
    if review:
        db.session.delete(review)
        db.session.commit()
        flash('Review deleted!', 'success')
    return redirect(url_for('admin.reviews'))

# --- COUPON ROUTES ---
@admin_bp.route('/admin/coupons')
@admin_required
def coupons():
    all_coupons = Coupon.query.all()
    return render_template('admin/coupons.html', coupons=all_coupons)

@admin_bp.route('/admin/coupon/new', methods=['GET', 'POST'])
@admin_required
def new_coupon():
    if request.method == 'POST':
        code = request.form.get('code').upper()
        type = request.form.get('type')
        discount = float(request.form.get('discount', 0))
        threshold = float(request.form.get('threshold', 0))
        usage_limit = int(request.form.get('usage_limit', 1))
        expiry_date_str = request.form.get('expiry_date')
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d') if expiry_date_str else None
        is_active = True if request.form.get('is_active') == 'on' else False

        coupon = Coupon(
            code=code, type=type, discount=discount,
            threshold=threshold, usage_limit=usage_limit,
            expiry_date=expiry_date, is_active=is_active
        )
        db.session.add(coupon)
        db.session.commit()
        flash('Coupon created successfully!', 'success')
        return redirect(url_for('admin.coupons'))
    return render_template('admin/coupon_form.html')

@admin_bp.route('/admin/coupon/delete/<int:id>', methods=['POST'])
@admin_required
def delete_coupon(id):
    coupon = db.session.get(Coupon, id)
    if coupon:
        db.session.delete(coupon)
        db.session.commit()
        flash('Coupon deleted!', 'success')
    return redirect(url_for('admin.coupons'))

# --- INVENTORY MANAGEMENT ROUTES ---
@admin_bp.route('/admin/inventory')
@admin_required
def inventory():
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', 'all')
    status_filter = request.args.get('stock_status', 'all')
    type_filter = request.args.get('product_type', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    # Overall Stock Statistics
    total_products = Product.query.count()
    instock_products = Product.query.filter_by(stock_status='instock').count()
    outofstock_products = Product.query.filter_by(stock_status='outofstock').count()
    total_variations = ProductVariation.query.count()
    instock_variations = ProductVariation.query.filter_by(stock_status='instock').count()
    outofstock_variations = ProductVariation.query.filter_by(stock_status='outofstock').count()

    stats = {
        'total_products': total_products,
        'instock_products': instock_products,
        'outofstock_products': outofstock_products,
        'total_variations': total_variations,
        'instock_variations': instock_variations,
        'outofstock_variations': outofstock_variations
    }

    # Query with eager loading
    query = Product.query.options(
        selectinload(Product.category),
        selectinload(Product.subcategory),
        selectinload(Product.attributes).selectinload(ProductAttribute.attribute),
        selectinload(Product.variations).selectinload(ProductVariation.options).selectinload(VariationOption.attribute_value)
    )

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%") | Product.id.ilike(f"%{search}%"))

    if category_filter != 'all':
        query = query.filter(Product.cat_name == category_filter)

    if status_filter != 'all':
        query = query.filter(Product.stock_status == status_filter)

    if type_filter != 'all':
        query = query.filter(Product.product_type == type_filter)

    pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    categories = Category.query.all()

    return render_template('admin/inventory.html',
                           products=products,
                           pagination=pagination,
                           categories=categories,
                           stats=stats,
                           search=search,
                           category_filter=category_filter,
                           status_filter=status_filter,
                           type_filter=type_filter)

@admin_bp.route('/admin/inventory/toggle-stock/<product_id>', methods=['POST'])
@admin_required
def toggle_product_stock(product_id):
    validate_csrf()
    product = db.session.get(Product, product_id)
    if not product:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        flash('Product not found.', 'error')
        return redirect(url_for('admin.inventory'))

    product.stock_status = 'outofstock' if product.stock_status == 'instock' else 'instock'
    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'product_id': product.id,
            'new_status': product.stock_status,
            'message': f"Stock status for '{product.name}' updated to {product.stock_status}."
        })

    flash(f"Stock status for '{product.name}' updated to {product.stock_status}.", 'success')
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/admin/inventory/toggle-variation-stock/<int:variation_id>', methods=['POST'])
@admin_required
def toggle_variation_stock(variation_id):
    validate_csrf()
    var = db.session.get(ProductVariation, variation_id)
    if not var:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Variation not found'}), 404
        flash('Variation not found.', 'error')
        return redirect(url_for('admin.inventory'))

    var.stock_status = 'outofstock' if var.stock_status == 'instock' else 'instock'
    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'variation_id': var.id,
            'new_status': var.stock_status,
            'message': f"Variation stock status updated to {var.stock_status}."
        })

    flash("Variation stock status updated.", 'success')
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/admin/inventory/quick-update', methods=['POST'])
@admin_required
def quick_update_inventory():
    validate_csrf()
    product_id = request.form.get('product_id') or (request.json.get('product_id') if request.is_json else None)
    price = request.form.get('price') or (request.json.get('price') if request.is_json else None)
    orig = request.form.get('orig') or (request.json.get('orig') if request.is_json else None)
    stock_status = request.form.get('stock_status') or (request.json.get('stock_status') if request.is_json else None)

    product = db.session.get(Product, product_id) if product_id else None
    if not product:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        flash('Product not found.', 'error')
        return redirect(url_for('admin.inventory'))

    if price is not None:
        product.price = price
    if orig is not None:
        product.orig = orig
    if stock_status in ['instock', 'outofstock']:
        product.stock_status = stock_status

    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'product_id': product.id,
            'price': product.price,
            'orig': product.orig,
            'stock_status': product.stock_status,
            'message': f"Updated inventory details for {product.name}."
        })

    flash(f"Updated inventory details for {product.name}.", 'success')
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/admin/inventory/update-variation', methods=['POST'])
@admin_required
def update_variation_inventory():
    validate_csrf()
    variation_id = request.form.get('variation_id') or (request.json.get('variation_id') if request.is_json else None)
    price = request.form.get('price') or (request.json.get('price') if request.is_json else None)
    stock_status = request.form.get('stock_status') or (request.json.get('stock_status') if request.is_json else None)

    var = db.session.get(ProductVariation, int(variation_id)) if variation_id else None
    if not var:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Variation not found'}), 404
        flash('Variation not found.', 'error')
        return redirect(url_for('admin.inventory'))

    if price is not None:
        var.price = price
    if stock_status in ['instock', 'outofstock']:
        var.stock_status = stock_status

    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'variation_id': var.id,
            'price': var.price,
            'stock_status': var.stock_status,
            'message': 'Variation details updated.'
        })

    flash('Variation details updated.', 'success')
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/admin/inventory/bulk-update', methods=['POST'])
@admin_required
def bulk_update_inventory():
    validate_csrf()
    action = request.form.get('bulk_action')
    product_ids = request.form.getlist('product_ids')

    if not product_ids:
        flash('No products selected for bulk action.', 'warning')
        return redirect(url_for('admin.inventory'))

    if action == 'mark_instock':
        Product.query.filter(Product.id.in_(product_ids)).update({Product.stock_status: 'instock'}, synchronize_session=False)
        db.session.commit()
        flash(f'Marked {len(product_ids)} product(s) as In Stock.', 'success')
    elif action == 'mark_outofstock':
        Product.query.filter(Product.id.in_(product_ids)).update({Product.stock_status: 'outofstock'}, synchronize_session=False)
        db.session.commit()
        flash(f'Marked {len(product_ids)} product(s) as Out of Stock.', 'success')
    else:
        flash('Invalid bulk action specified.', 'error')

    return redirect(url_for('admin.inventory'))


