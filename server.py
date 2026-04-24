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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://extravagantmeals_user:V9EijyegMbl2Hcwn0Ajaj61ROYlXnOpH@dpg-d7ktnq8sfn5c73cqeto0-a.frankfurt-postgres.render.com/extravagantmeals'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', 'extravagant_meals_secret_key_2024')

cloudinary.config(
    cloud_name='ddusfl7pi',
    api_key='599965682593626',
    api_secret='pUcb90_1jtv-rDlHXRRsfDcBK5k'
)

db = SQLAlchemy(app)

# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'em_users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='user', lazy=True)

class Category(db.Model):
    __tablename__ = 'em_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    meals = db.relationship('Meal', backref='category', lazy=True)

class Meal(db.Model):
    __tablename__ = 'em_meals'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('em_categories.id'))
    image_url = db.Column(db.Text)
    video_url = db.Column(db.Text)
    cloudinary_image_id = db.Column(db.Text)
    cloudinary_video_id = db.Column(db.Text)
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    __tablename__ = 'em_orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('em_users.id'), nullable=True)
    guest_name = db.Column(db.String(100))
    guest_email = db.Column(db.String(150))
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, paid, preparing, delivered, cancelled
    payment_ref = db.Column(db.String(200))
    # Delivery info
    delivery_address = db.Column(db.Text)
    delivery_city = db.Column(db.String(100))
    delivery_state = db.Column(db.String(100))
    delivery_phone = db.Column(db.String(30))
    delivery_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    __tablename__ = 'em_order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('em_orders.id'))
    meal_id = db.Column(db.Integer, db.ForeignKey('em_meals.id'))
    meal_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    meal = db.relationship('Meal')

# ─── HELPERS ──────────────────────────────────────────────────────────────────

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

def meal_to_dict(meal):
    return {
        'id': meal.id,
        'name': meal.name,
        'description': meal.description,
        'price': meal.price,
        'category': meal.category.name if meal.category else None,
        'category_id': meal.category_id,
        'image_url': meal.image_url,
        'video_url': meal.video_url,
        'is_available': meal.is_available,
        'is_featured': meal.is_featured,
        'created_at': meal.created_at.isoformat()
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
        'delivery_address': order.delivery_address,
        'delivery_city': order.delivery_city,
        'delivery_state': order.delivery_state,
        'delivery_phone': order.delivery_phone,
        'delivery_note': order.delivery_note,
        'created_at': order.created_at.isoformat(),
        'items': [{
            'meal_id': i.meal_id,
            'meal_name': i.meal_name,
            'quantity': i.quantity,
            'unit_price': i.unit_price,
            'subtotal': i.quantity * i.unit_price
        } for i in order.items]
    }

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

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
    return jsonify({'token': token, 'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json()
    email = d.get('email', '').strip().lower()
    password = d.get('password', '')
    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return jsonify({'error': 'Invalid email or password'}), 401
    token = make_token(user.id, user.is_admin)
    return jsonify({'token': token, 'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}})

@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    user = User.query.get(request.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin})

# ─── CATEGORIES ───────────────────────────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def get_categories():
    cats = Category.query.all()
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

@app.route('/api/admin/categories/<int:cid>', methods=['DELETE'])
@admin_required
def delete_category(cid):
    cat = Category.query.get_or_404(cid)
    # Unlink meals from this category before deleting
    for meal in cat.meals:
        meal.category_id = None
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': 'Deleted'})

# ─── MEALS ────────────────────────────────────────────────────────────────────

@app.route('/api/meals', methods=['GET'])
def get_meals():
    category = request.args.get('category')
    featured = request.args.get('featured')
    q = Meal.query.filter_by(is_available=True)
    if category:
        cat = Category.query.filter_by(slug=category).first()
        if cat:
            q = q.filter_by(category_id=cat.id)
    if featured:
        q = q.filter_by(is_featured=True)
    meals = q.order_by(Meal.created_at.desc()).all()
    return jsonify([meal_to_dict(m) for m in meals])

@app.route('/api/meals/<int:mid>', methods=['GET'])
def get_meal(mid):
    meal = Meal.query.get_or_404(mid)
    return jsonify(meal_to_dict(meal))

@app.route('/api/admin/meals', methods=['GET'])
@admin_required
def admin_get_meals():
    meals = Meal.query.order_by(Meal.created_at.desc()).all()
    return jsonify([meal_to_dict(m) for m in meals])

@app.route('/api/admin/meals', methods=['POST'])
@admin_required
def create_meal():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price = request.form.get('price')
    category_id = request.form.get('category_id')
    is_featured = request.form.get('is_featured', 'false') == 'true'
    is_available = request.form.get('is_available', 'true') == 'true'

    if not name or not price:
        return jsonify({'error': 'Name and price required'}), 400

    meal = Meal(
        name=name,
        description=description,
        price=float(price),
        category_id=int(category_id) if category_id else None,
        is_featured=is_featured,
        is_available=is_available
    )

    image_file = request.files.get('image')
    if image_file:
        result = cloudinary.uploader.upload(image_file, folder='extravagant_meals/images')
        meal.image_url = result['secure_url']
        meal.cloudinary_image_id = result['public_id']

    video_file = request.files.get('video')
    if video_file:
        result = cloudinary.uploader.upload(video_file, resource_type='video', folder='extravagant_meals/videos')
        meal.video_url = result['secure_url']
        meal.cloudinary_video_id = result['public_id']

    db.session.add(meal)
    db.session.commit()
    return jsonify(meal_to_dict(meal)), 201

@app.route('/api/admin/meals/<int:mid>', methods=['PUT'])
@admin_required
def update_meal(mid):
    meal = Meal.query.get_or_404(mid)
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    category_id = request.form.get('category_id')
    is_featured = request.form.get('is_featured')
    is_available = request.form.get('is_available')

    if name: meal.name = name.strip()
    if description is not None: meal.description = description.strip()
    if price: meal.price = float(price)
    if category_id: meal.category_id = int(category_id)
    if is_featured is not None: meal.is_featured = is_featured == 'true'
    if is_available is not None: meal.is_available = is_available == 'true'

    image_file = request.files.get('image')
    if image_file:
        if meal.cloudinary_image_id:
            cloudinary.uploader.destroy(meal.cloudinary_image_id)
        result = cloudinary.uploader.upload(image_file, folder='extravagant_meals/images')
        meal.image_url = result['secure_url']
        meal.cloudinary_image_id = result['public_id']

    video_file = request.files.get('video')
    if video_file:
        if meal.cloudinary_video_id:
            cloudinary.uploader.destroy(meal.cloudinary_video_id, resource_type='video')
        result = cloudinary.uploader.upload(video_file, resource_type='video', folder='extravagant_meals/videos')
        meal.video_url = result['secure_url']
        meal.cloudinary_video_id = result['public_id']

    db.session.commit()
    return jsonify(meal_to_dict(meal))

@app.route('/api/admin/meals/<int:mid>', methods=['DELETE'])
@admin_required
def delete_meal(mid):
    meal = Meal.query.get_or_404(mid)
    if meal.cloudinary_image_id:
        cloudinary.uploader.destroy(meal.cloudinary_image_id)
    if meal.cloudinary_video_id:
        cloudinary.uploader.destroy(meal.cloudinary_video_id, resource_type='video')
    db.session.delete(meal)
    db.session.commit()
    return jsonify({'message': 'Meal deleted'})

# ─── ORDERS ───────────────────────────────────────────────────────────────────

@app.route('/api/orders', methods=['POST'])
def create_order():
    d = request.get_json()
    items = d.get('items', [])
    delivery = d.get('delivery', {})
    if not items:
        return jsonify({'error': 'No items in order'}), 400

    total = 0
    order_items = []
    for item in items:
        meal = Meal.query.get(item['meal_id'])
        if not meal or not meal.is_available:
            return jsonify({'error': f'Meal {item["meal_id"]} not available'}), 400
        qty = int(item['quantity'])
        total += meal.price * qty
        order_items.append(OrderItem(
            meal_id=meal.id,
            meal_name=meal.name,
            quantity=qty,
            unit_price=meal.price
        ))

    # Try to get user from token if provided
    user_id = None
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            user_id = data['user_id']
        except:
            pass

    order = Order(
        user_id=user_id,
        guest_name=delivery.get('name'),
        guest_email=delivery.get('email'),
        total_amount=total,
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

# ─── ADMIN ORDERS ─────────────────────────────────────────────────────────────

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
    order = Order.query.get_or_404(oid)
    d = request.get_json()
    status = d.get('status')
    if status not in ['pending', 'paid', 'preparing', 'delivered', 'cancelled']:
        return jsonify({'error': 'Invalid status'}), 400
    order.status = status
    db.session.commit()
    return jsonify({'message': 'Updated', 'status': status})

# ─── ADMIN STATS ──────────────────────────────────────────────────────────────

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    total_orders = Order.query.count()
    paid_orders = Order.query.filter_by(status='paid').count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter(Order.status == 'paid').scalar() or 0
    total_meals = Meal.query.count()
    total_users = User.query.count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return jsonify({
        'total_orders': total_orders,
        'paid_orders': paid_orders,
        'total_revenue': total_revenue,
        'total_meals': total_meals,
        'total_users': total_users,
        'recent_orders': [order_to_dict(o) for o in recent_orders]
    })

# ─── ADMIN USER MANAGEMENT ────────────────────────────────────────────────────

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{'id': u.id, 'name': u.name, 'email': u.email, 'is_admin': u.is_admin, 'created_at': u.created_at.isoformat()} for u in users])

@app.route('/api/admin/users/<int:uid>/make-admin', methods=['PUT'])
@admin_required
def make_admin_user(uid):
    user = User.query.get_or_404(uid)
    user.is_admin = True
    db.session.commit()
    return jsonify({'message': f'{user.name} is now an admin'})

# ─── INIT DB & SEED ───────────────────────────────────────────────────────────

@app.route('/api/init', methods=['GET', 'POST'])
def init_db():
    db.create_all()

    # Seed default admin
    if not User.query.filter_by(email='admin@extravagantmeals.com').first():
        hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
        admin = User(name='Admin', email='admin@extravagantmeals.com', password_hash=hashed, is_admin=True)
        db.session.add(admin)

    # Seed default categories — no Grills or Desserts
    default_cats = ['Starters', 'Main Course', 'Soups', 'Drinks']
    for cat_name in default_cats:
        slug = cat_name.lower().replace(' ', '-')
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name=cat_name, slug=slug))

    db.session.commit()
    return jsonify({'message': 'Database initialized and seeded'})

@app.route('/')
def health():
    return jsonify({'status': 'Extravagant Meals API running'})

if __name__ == '__main__':
    app.run(debug=True)