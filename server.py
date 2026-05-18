import os
import jwt
import bcrypt
import cloudinary
import cloudinary.uploader
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*")

# ─── CONFIG ──────────────────────────────────────────────────────────────────
_db_url = os.environ.get(
    'DATABASE_URL',
    'postgresql://extravagantmeals_user:V9EijyegMbl2Hcwn0Ajaj61ROYlXnOpH@dpg-d7ktnq8sfn5c73cqeto0-a.frankfurt-postgres.render.com/extravagantmeals'
)
# Render provides postgres:// but SQLAlchemy 1.4+ requires postgresql://
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', 'dera_electronics_secret_key_2024')

cloudinary.config(
    cloud_name='ddusfl7pi',
    api_key='599965682593626',
    api_secret='pUcb90_1jtv-rDlHXRRsfDcBK5k'
)

db = SQLAlchemy(app)

# ─── MODELS ──────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'dera_users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='user', lazy=True)

class Category(db.Model):
    __tablename__ = 'dera_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    __tablename__ = 'dera_products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('dera_categories.id'))
    image_url = db.Column(db.Text)
    video_url = db.Column(db.Text)
    cloudinary_image_id = db.Column(db.Text)
    cloudinary_video_id = db.Column(db.Text)
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    __tablename__ = 'dera_orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('dera_users.id'), nullable=True)
    guest_name = db.Column(db.String(100))
    guest_email = db.Column(db.String(150))
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    payment_ref = db.Column(db.String(200))
    selected_account = db.Column(db.String(100))
    delivery_address = db.Column(db.Text)
    delivery_city = db.Column(db.String(100))
    delivery_state = db.Column(db.String(100))
    delivery_phone = db.Column(db.String(30))
    delivery_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    __tablename__ = 'dera_order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('dera_orders.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('dera_products.id'))
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def make_token(user_id, is_admin=False):
    payload = {
        'user_id': user_id,
        'is_admin': is_admin,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            request.user_id = data['user_id']
            request.is_admin = data.get('is_admin', False)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            if not data.get('is_admin'):
                return jsonify({'error': 'Admin access required'}), 403
            request.user_id = data['user_id']
            request.is_admin = True
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def product_to_dict(p):
    return {
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'price': p.price,
        'category': p.category.name if p.category else None,
        'category_id': p.category_id,
        'image_url': p.image_url,
        'video_url': p.video_url,
        'is_available': p.is_available,
        'is_featured': p.is_featured,
        'created_at': p.created_at.isoformat()
    }

def order_to_dict(order):
    return {
        'id': order.id,
        'user_id': order.user_id,
        'guest_name': order.guest_name,
        'guest_email': order.guest_email,
        'total_amount': order.total_amount,
        'status': order.status,
        'payment_ref': order.payment_ref,
        'selected_account': order.selected_account,
        'delivery_address': order.delivery_address,
        'delivery_city': order.delivery_city,
        'delivery_state': order.delivery_state,
        'delivery_phone': order.delivery_phone,
        'delivery_note': order.delivery_note,
        'created_at': order.created_at.isoformat(),
        'items': [{
            'product_id': i.product_id,
            'product_name': i.product_name,
            'quantity': i.quantity,
            'unit_price': i.unit_price,
            'subtotal': i.quantity * i.unit_price
        } for i in order.items]
    }

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    d = request.get_json()
    name = d.get('name', '').strip()
    email = d.get('email', '').strip().lower()
    password = d.get('password', '')
    if not name or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(name=name, email=email, password_hash=hashed)
    db.session.add(user)
    db.session.commit()
    token = make_token(user.id, user.is_admin)
    return jsonify({
        'token': token,
        'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json()
    email = d.get('email', '').strip().lower()
    password = d.get('password', '')
    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return jsonify({'error': 'Invalid email or password'}), 401
    token = make_token(user.id, user.is_admin)
    return jsonify({
        'token': token,
        'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}
    })

@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin})

# ─── CATEGORIES ──────────────────────────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def get_categories():
    cats = Category.query.order_by(Category.name).all()
    return jsonify([{'id': c.id, 'name': c.name, 'slug': c.slug} for c in cats])

@app.route('/api/admin/categories', methods=['POST'])
@admin_required
def create_category():
    d = request.get_json()
    name = d.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Category name required'}), 400
    slug = name.lower().replace(' ', '-')
    if Category.query.filter_by(slug=slug).first():
        return jsonify({'error': 'Category already exists'}), 409
    cat = Category(name=name, slug=slug)
    db.session.add(cat)
    db.session.commit()
    return jsonify({'id': cat.id, 'name': cat.name, 'slug': cat.slug}), 201

@app.route('/api/admin/categories/<int:cid>', methods=['PUT'])
@admin_required
def update_category(cid):
    cat = db.session.get(Category, cid)
    if not cat:
        return jsonify({'error': 'Category not found'}), 404
    d = request.get_json()
    name = d.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Category name required'}), 400
    new_slug = name.lower().replace(' ', '-')
    existing = Category.query.filter_by(slug=new_slug).first()
    if existing and existing.id != cid:
        return jsonify({'error': 'Category name already exists'}), 409
    cat.name = name
    cat.slug = new_slug
    db.session.commit()
    return jsonify({'id': cat.id, 'name': cat.name, 'slug': cat.slug})

@app.route('/api/admin/categories/<int:cid>', methods=['DELETE'])
@admin_required
def delete_category(cid):
    cat = db.session.get(Category, cid)
    if not cat:
        return jsonify({'error': 'Category not found'}), 404
    for p in cat.products:
        p.category_id = None
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': 'Category deleted'})

# ─── PRODUCTS ────────────────────────────────────────────────────────────────

@app.route('/api/products', methods=['GET'])
def get_products():
    category = request.args.get('category')
    featured = request.args.get('featured')
    search = request.args.get('search', '').strip()
    q = Product.query.filter_by(is_available=True)
    if category and category != 'all':
        cat = Category.query.filter_by(slug=category).first()
        if cat:
            q = q.filter_by(category_id=cat.id)
    if featured:
        q = q.filter_by(is_featured=True)
    if search:
        q = q.filter(Product.name.ilike(f'%{search}%'))
    products = q.order_by(Product.created_at.desc()).all()
    return jsonify([product_to_dict(p) for p in products])

@app.route('/api/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = db.session.get(Product, pid)
    if not p:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify(product_to_dict(p))

@app.route('/api/admin/products', methods=['GET'])
@admin_required
def admin_get_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return jsonify([product_to_dict(p) for p in products])

@app.route('/api/admin/products', methods=['POST'])
@admin_required
def create_product():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price = request.form.get('price')
    category_id = request.form.get('category_id')
    is_featured = request.form.get('is_featured', 'false') == 'true'
    is_available = request.form.get('is_available', 'true') == 'true'

    if not name or not price:
        return jsonify({'error': 'Name and price required'}), 400

    product = Product(
        name=name,
        description=description,
        price=float(price),
        category_id=int(category_id) if category_id else None,
        is_featured=is_featured,
        is_available=is_available
    )

    image_file = request.files.get('image')
    if image_file:
        result = cloudinary.uploader.upload(image_file, folder='dera_electronics/images')
        product.image_url = result['secure_url']
        product.cloudinary_image_id = result['public_id']

    video_file = request.files.get('video')
    if video_file:
        result = cloudinary.uploader.upload(video_file, resource_type='video', folder='dera_electronics/videos')
        product.video_url = result['secure_url']
        product.cloudinary_video_id = result['public_id']

    db.session.add(product)
    db.session.commit()
    return jsonify(product_to_dict(product)), 201

@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@admin_required
def update_product(pid):
    product = db.session.get(Product, pid)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    category_id = request.form.get('category_id')
    is_featured = request.form.get('is_featured')
    is_available = request.form.get('is_available')

    if name: product.name = name.strip()
    if description is not None: product.description = description.strip()
    if price: product.price = float(price)
    if category_id is not None:
        product.category_id = int(category_id) if category_id else None
    if is_featured is not None: product.is_featured = is_featured == 'true'
    if is_available is not None: product.is_available = is_available == 'true'

    image_file = request.files.get('image')
    if image_file:
        if product.cloudinary_image_id:
            try: cloudinary.uploader.destroy(product.cloudinary_image_id)
            except: pass
        result = cloudinary.uploader.upload(image_file, folder='dera_electronics/images')
        product.image_url = result['secure_url']
        product.cloudinary_image_id = result['public_id']

    video_file = request.files.get('video')
    if video_file:
        if product.cloudinary_video_id:
            try: cloudinary.uploader.destroy(product.cloudinary_video_id, resource_type='video')
            except: pass
        result = cloudinary.uploader.upload(video_file, resource_type='video', folder='dera_electronics/videos')
        product.video_url = result['secure_url']
        product.cloudinary_video_id = result['public_id']

    db.session.commit()
    return jsonify(product_to_dict(product))

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@admin_required
def delete_product(pid):
    product = db.session.get(Product, pid)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    if product.cloudinary_image_id:
        try: cloudinary.uploader.destroy(product.cloudinary_image_id)
        except: pass
    if product.cloudinary_video_id:
        try: cloudinary.uploader.destroy(product.cloudinary_video_id, resource_type='video')
        except: pass
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'})

@app.route('/api/admin/products/<int:pid>/toggle-featured', methods=['PUT'])
@admin_required
def toggle_featured(pid):
    product = db.session.get(Product, pid)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    product.is_featured = not product.is_featured
    db.session.commit()
    return jsonify({'id': product.id, 'is_featured': product.is_featured})

@app.route('/api/admin/products/<int:pid>/toggle-available', methods=['PUT'])
@admin_required
def toggle_available(pid):
    product = db.session.get(Product, pid)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    product.is_available = not product.is_available
    db.session.commit()
    return jsonify({'id': product.id, 'is_available': product.is_available})

# ─── ORDERS ──────────────────────────────────────────────────────────────────

@app.route('/api/orders', methods=['POST'])
def create_order():
    d = request.get_json()
    items = d.get('items', [])
    delivery = d.get('delivery', {})
    selected_account = d.get('selected_account', '')

    if not items:
        return jsonify({'error': 'No items in order'}), 400

    total = 0
    order_items = []
    for item in items:
        product = Product.query.get(item['product_id'])
        if not product or not product.is_available:
            return jsonify({'error': f'Product {item["product_id"]} not available'}), 400
        qty = int(item['quantity'])
        total += product.price * qty
        order_items.append(OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            unit_price=product.price
        ))

    user_id = None
    token_str = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token_str:
        try:
            data = jwt.decode(token_str, app.config['JWT_SECRET'], algorithms=['HS256'])
            user_id = data['user_id']
        except:
            pass

    order = Order(
        user_id=user_id,
        guest_name=delivery.get('name'),
        guest_email=delivery.get('email'),
        total_amount=total,
        selected_account=selected_account,
        delivery_address=delivery.get('address'),
        delivery_city=delivery.get('city'),
        delivery_state=delivery.get('state'),
        delivery_phone=delivery.get('phone'),
        delivery_note=delivery.get('note'),
        status='pending'
    )
    db.session.add(order)
    db.session.flush()
    for oi in order_items:
        oi.order_id = order.id
        db.session.add(oi)
    db.session.commit()
    return jsonify({'order_id': order.id, 'total': total}), 201

@app.route('/api/orders/my', methods=['GET'])
@token_required
def my_orders():
    orders = Order.query.filter_by(user_id=request.user_id).order_by(Order.created_at.desc()).all()
    return jsonify([order_to_dict(o) for o in orders])

@app.route('/api/orders/<int:oid>', methods=['GET'])
@token_required
def get_order(oid):
    order = db.session.get(Order, oid)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    if order.user_id != request.user_id and not request.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    return jsonify(order_to_dict(order))

# ─── ADMIN ORDERS ────────────────────────────────────────────────────────────

@app.route('/api/admin/orders', methods=['GET'])
@admin_required
def admin_get_orders():
    status = request.args.get('status')
    q = Order.query
    if status:
        q = q.filter_by(status=status)
    orders = q.order_by(Order.created_at.desc()).all()
    return jsonify([order_to_dict(o) for o in orders])

@app.route('/api/admin/orders/<int:oid>/status', methods=['PUT'])
@admin_required
def update_order_status(oid):
    order = db.session.get(Order, oid)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    d = request.get_json()
    status = d.get('status')
    if status not in ['pending', 'paid', 'preparing', 'delivered', 'cancelled']:
        return jsonify({'error': 'Invalid status'}), 400
    order.status = status
    if d.get('payment_ref'):
        order.payment_ref = d['payment_ref']
    db.session.commit()
    return jsonify({'message': 'Status updated', 'status': status})

@app.route('/api/admin/orders/<int:oid>', methods=['DELETE'])
@admin_required
def delete_order(oid):
    order = db.session.get(Order, oid)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    for item in order.items:
        db.session.delete(item)
    db.session.delete(order)
    db.session.commit()
    return jsonify({'message': 'Order deleted'})

# ─── ADMIN STATS ─────────────────────────────────────────────────────────────

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    total_orders = Order.query.count()
    paid_orders = Order.query.filter_by(status='paid').count()
    pending_orders = Order.query.filter_by(status='pending').count()
    preparing_orders = Order.query.filter_by(status='preparing').count()
    delivered_orders = Order.query.filter_by(status='delivered').count()
    cancelled_orders = Order.query.filter_by(status='cancelled').count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.status.in_(['paid', 'preparing', 'delivered'])
    ).scalar() or 0
    total_products = Product.query.count()
    available_products = Product.query.filter_by(is_available=True).count()
    featured_products = Product.query.filter_by(is_featured=True).count()
    total_users = User.query.count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return jsonify({
        'total_orders': total_orders,
        'paid_orders': paid_orders,
        'pending_orders': pending_orders,
        'preparing_orders': preparing_orders,
        'delivered_orders': delivered_orders,
        'cancelled_orders': cancelled_orders,
        'total_revenue': total_revenue,
        'total_products': total_products,
        'available_products': available_products,
        'featured_products': featured_products,
        'total_users': total_users,
        'recent_orders': [order_to_dict(o) for o in recent_orders]
    })

# ─── ADMIN USERS ─────────────────────────────────────────────────────────────

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'is_admin': u.is_admin,
        'created_at': u.created_at.isoformat(),
        'order_count': len(u.orders)
    } for u in users])

@app.route('/api/admin/users/<int:uid>/make-admin', methods=['PUT'])
@admin_required
def make_admin_user(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    user.is_admin = True
    db.session.commit()
    return jsonify({'message': f'{user.name} is now an admin'})

@app.route('/api/admin/users/<int:uid>/remove-admin', methods=['PUT'])
@admin_required
def remove_admin_user(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.email == 'admin@deraelectronics.com':
        return jsonify({'error': 'Cannot remove superadmin'}), 403
    user.is_admin = False
    db.session.commit()
    return jsonify({'message': f'{user.name} admin access removed'})

@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.email == 'admin@deraelectronics.com':
        return jsonify({'error': 'Cannot delete superadmin'}), 403
    # Detach orders so FK constraint doesn't block deletion
    Order.query.filter_by(user_id=uid).update({'user_id': None})
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'})

# ─── INIT DB ─────────────────────────────────────────────────────────────────

@app.route('/api/init', methods=['GET', 'POST'])
def init_db():
    db.create_all()

    if not User.query.filter_by(email='admin@deraelectronics.com').first():
        hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
        admin = User(name='Admin', email='admin@deraelectronics.com', password_hash=hashed, is_admin=True)
        db.session.add(admin)

    default_cats = ['Speakers', 'Washing Machines', 'Gas Cookers', 'Televisions', 'Refrigerators', 'Air Conditioners']
    for cat_name in default_cats:
        slug = cat_name.lower().replace(' ', '-')
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name=cat_name, slug=slug))

    db.session.commit()
    return jsonify({'message': 'Dera Electronics database initialized and seeded'})

@app.route('/')
def health():
    return jsonify({'status': 'Dera of Alaba Electronics API running'})

# ─── AUTO-INIT ON STARTUP ─────────────────────────────────────────────────────
# Creates all tables and seeds admin + default categories automatically.
# Safe to run on every deploy — uses IF NOT EXISTS logic under the hood.
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@deraelectronics.com').first():
        hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
        admin = User(name='Admin', email='admin@deraelectronics.com', password_hash=hashed, is_admin=True)
        db.session.add(admin)
    default_cats = ['Speakers', 'Washing Machines', 'Gas Cookers', 'Televisions', 'Refrigerators', 'Air Conditioners']
    for cat_name in default_cats:
        slug = cat_name.lower().replace(' ', '-')
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name=cat_name, slug=slug))
    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)