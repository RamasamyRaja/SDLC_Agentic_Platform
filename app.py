from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager,jwt_required,get_jwt_identity
import jwt
import uuid
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
from flask_bcrypt import Bcrypt, check_password_hash
from functools import wraps
import razorpay
from flask_cors import CORS


from models import db, User, Product, Cart, Order, Payment
from routes.users import users_bp,generate_token
from routes.cart import cart_bp
from payments import payments_bp
from routes.orders import orders_bp


# ✅ Secret Key
SECRET_KEY = 'super_secret_key'

# ✅ Flask App Init
app = Flask(__name__)
bcrypt = Bcrypt(app)
app.secret_key = SECRET_KEY

# ✅ Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:XXXXXXXXX@localhost/lume_luxe' 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# ✅ JWT Config
app.config['JWT_SECRET_KEY'] = SECRET_KEY
jwt = JWTManager(app)

CORS(app)

# ✅ Razorpay Config
app.config["RAZORPAY_KEY"] = "YOUR_KEY_HERE"
app.config["RAZORPAY_SECRET"] = "YOUR_SECRET_KEY_HERE" 
razorpay_client = razorpay.Client(auth=(app.config["RAZORPAY_KEY"], app.config["RAZORPAY_SECRET"]))

# ✅ Blueprints
app.register_blueprint(users_bp, url_prefix='/users')
app.register_blueprint(cart_bp, url_prefix='/')
app.register_blueprint(payments_bp, url_prefix='/api/payments')
app.register_blueprint(orders_bp, url_prefix='/api/payments')


# ✅ Custom Token Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split()[1]
        if not token:
            return jsonify({'error': 'Token is missing!'}), 403
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_email = data['email']
        except:
            return jsonify({'error': 'Token is invalid or expired!'}), 403
        return f(current_user_email, *args, **kwargs)
    return decorated

# ✅ Sample Product Data
products_data = {
    1: {"id": 1, "name": "Casual T-Shirt", "price": 599, "image": "tshirt1.jpg"},
    2: {"id": 2, "name": "Printed T-Shirt", "price": 699, "image": "tshirt2.jpg"},
    3: {"id": 3, "name": "Solid T-Shirt", "price": 799, "image": "tshirt3.jpg"},
    4: {"id": 4, "name": "Formal Pants", "price": 999, "image": "pants1.jpg"},
    5: {"id": 5, "name": "Black Pants", "price": 1199, "image": "pants2.jpg"},
    6: {"id": 6, "name": "Chinos", "price": 899, "image": "pants3.jpg"},
    7: {"id": 7, "name": "Printed Shirt", "price": 899, "image": "formalshirt1.jpg"},
    8: {"id": 8, "name": "Shirt", "price": 1099, "image": "formalshirt2.jpg"},
    9: {"id": 9, "name": "Purple Shirt", "price": 999, "image": "formalshirt3.jpg"},
    10:{"id": 10, "name": "Brown Premium", "price": 1399, "image": "wallet1.jpg"},
    11: {"id": 11, "name": "Olive Green", "price": 1559, "image": "wallet2.jpg"},
    12: {"id": 12, "name": "Rarerabbit", "price": 4999, "image": "wallet3.jpg"},
    13: {"id": 13, "name": "Embroidered Salwar", "price": 1000, "image": "womensalwar1.jpg"},
    14: {"id": 14, "name": "Printed Salwar", "price": 1650, "image": "womensalwar2.jpg"},
    15: {"id": 15, "name": "Salwar", "price": 1700, "image": "womensalwar3.jpg"},
    16: {"id": 16, "name": "High-Waist Jeans", "price": 800, "image": "woments1.jpg"},
    17: {"id": 17, "name": "Graphic Tee", "price": 1500, "image": "woments2.jpg"},
    18: {"id": 18, "name": "Jean & T-Shirt", "price": 1700, "image": "woments3.jpg"},
    19: {"id": 19 , "name": "Jumpsuit", "price":1800, "image": "womensuits1.jpg"},
    20: {"id": 20, "name": "Printed Jumpsuit", "price": 1500, "image": "womensuits2.jpg"},
    21: {"id": 21, "name": "Formal Jumpsuit", "price": 1100, "image": "womensuits3.jpg"},
    22: {"id": 22, "name": "Matte Lipstick", "price": 399, "image": "womenlp1.jpg"},
    23: {"id": 23, "name": "Glossy Lipstick", "price": 349, "image": "womenlp2.jpg"},
    24: {"id": 24, "name": "Nude Shade", "price": 449, "image": "womenlp3.jpg"},
    25: {"id": 25, "name": "Pink", "price": 1200, "image": "womenbag1.jpg"},
    26: {"id": 26, "name": "Black", "price": 1500, "image": "womenbag2.jpg"},
    27: {"id": 27, "name": "Pearl White", "price": 1700, "image": "womenbag3.jpg"},
    28: {"id": 28, "name": "Strawberry Mask", "price": 299, "image": "Facemask1.jpg"},
    29: {"id": 29, "name": "Cucumber Mask", "price": 349, "image": "Facemask2.jpg"},
    30: {"id": 30, "name": "Frock", "price": 799, "image": "kidsdress1.jpg"},
    31: {"id": 31, "name": "Party Dress", "price": 999, "image": "kidsdress2.jpg"},
    32: {"id": 32, "name": "Boys Salwar", "price": 899, "image": "kidsdress3.jpg"},
    33: {"id": 33, "name": "Cartoon Tee", "price": 499, "image": "kjs1.jpg"},
    34: {"id": 34, "name": "Denim Jeans", "price": 699, "image": "kjs2.jpg"},
    35: {"id": 35, "name": "Printed T-Shirt", "price": 549, "image": "kjs3.jpg"},
    36: {"id": 36, "name": "Red Heels", "price": 2000, "image": "Footwear1.jpg"},
    37: {"id": 37, "name": "Lavendar Flats", "price": 1250, "image": "Footwear2.jpg"},
    38: {"id": 38, "name": "Cozy Casual Slipper", "price": 1500, "image": "Footwear5.jpg"},
    39: {"id": 39, "name": "Formal Shoes", "price": 2100, "image": "Footwear3.jpg"},
    40: {"id": 40, "name": "Navy Blue Shoes", "price": 2500, "image": "Footwear4.jpg"},
    41: {"id": 41, "name": "Girl Baby Shoe", "price": 1000, "image": "Footwear6.jpg"},
    42: {"id": 42, "name": "Strawberry Shoe", "price": 700, "image": "Footwear7.jpg"},
    43: {"id": 43, "name": "Boy Baby shoe", "price": 999, "image": "Footwear8.jpg"}
}

# ✅ Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/users/signup')
def signup_page():
    return render_template('signup.html')

@app.route('/users/login')
def login_page():
    return render_template('login.html')


@app.route('/product/<int:product_id>')
def product_page(product_id):
    product = products_data.get(product_id)
    if not product:
        return "Product Not Found", 404
    return render_template('productdetails.html', product=product)

@app.route('/cart')
def cart_page():
    return render_template("cart.html", razorpay_key=app.config["RAZORPAY_KEY"])

@app.route('/admin/dashboard')
@token_required
def admin_dashboard(current_admin):
    return f"Welcome to Admin Dashboard, {current_admin}!"

# ✅ Add to Cart
@app.route('/add_to_cart', methods=['POST'])
@jwt_required()
def add_to_cart():
    current_user_email = get_jwt_identity()
    data = request.get_json()
    user = User.query.filter_by(email=current_user_email).first()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    if not user or not product_id:
        return jsonify({'error': 'Missing data'}), 400

    try:
        quantity = int(quantity)
    except ValueError:
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    existing_item = Cart.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing_item:
        existing_item.quantity += quantity
    else:
        new_cart_item = Cart(user_id=user.id, product_id=product_id, quantity=quantity)
        db.session.add(new_cart_item)

    db.session.commit()
    return jsonify({"message": "Product added to cart!"})

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    admin = User.query.filter_by(email=email, is_admin=True).first()
    if admin and check_password_hash(admin.password, password):
        token = jwt.encode({
            'email': admin.email,
            'is_admin': True,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token})
    else:
        return jsonify({'error': 'Invalid admin credentials'}), 401


# ✅ View Cart
@app.route('/cart/view', methods=['GET'])
@token_required
def view_cart(current_user):
    cart_items = db.session.query(Cart, Product).join(Product, Cart.product_id == Product.id)\
        .filter(Cart.user_id == current_user).all()

    cart_data = [
        {
            'product_id': item.Cart.product_id,
            'quantity': item.Cart.quantity,
            'name': item.Product.name,
            'price': item.Product.price
        }
        for item in cart_items
    ]
    return jsonify({'cart': cart_data})

# ✅ Remove From Cart
@app.route('/cart/remove', methods=['DELETE'])
@token_required
def remove_from_cart(current_user):
    data = request.get_json()
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'error': 'Product ID is required'}), 400

    cart_item = Cart.query.filter_by(user_id=current_user, product_id=product_id).first()
    if not cart_item:
        return jsonify({'error': 'Item not found'}), 404

    db.session.delete(cart_item)
    db.session.commit()
    return jsonify({'message': 'Item removed from cart successfully'})


# ✅ Razorpay Order Route (You can expand on this in payments.py)
@app.route('/api/payments/create_order', methods=['POST'])
@jwt_required()
def create_order():
    user_email = get_jwt_identity()
    print("Request received!")
    print("Token identity:", get_jwt_identity())
    print("Incoming data:", request.get_json())
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    raw_quantity = data.get('quantity', 1)

    if isinstance(raw_quantity, bool) or not isinstance(raw_quantity, (int, str)):
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    if isinstance(raw_quantity, str) and not raw_quantity.strip().isdigit():
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    quantity = int(raw_quantity)
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    user = User.query.filter_by(email=user_email).first()
    product = Product.query.get(product_id)

    if not product:
        return jsonify({'error': 'Product not found'}), 404

    total_price = product.price * quantity
    tracking_id = 'TRK' + str(uuid.uuid4().hex[:8])

    payment = razorpay_client.order.create({
        "amount": int(total_price * 100),
        "currency": "INR",
        "payment_capture": 1
    })

    new_order = Order(
        user_id=user.id,
        product_id=product.id,
        quantity=quantity,
        total_price=total_price,
        tracking_id=tracking_id,
        razorpay_order_id=payment['id'],
        status="Processing"
    )
    db.session.add(new_order)
    db.session.commit()

    return jsonify({
        'order_id': payment['id'],
        'amount': total_price,
        'currency': 'INR',
        'razorpay_key': app.config["RAZORPAY_KEY"],
        'tracking_id': tracking_id
    })

@app.route('/your_cart_route', methods=['GET'])
@token_required
def get_cart(current_user_email):
    # Use current_user_email to query your DB and get user cart
    # Dummy example response:
    return jsonify({'message': f'Cart fetched for {current_user_email}'})

        
    
@app.route('/payment_success', methods=['POST'])
def payment_success():
    data = request.get_json()
    order_id = data.get('order_id')
    payment_id = data.get('payment_id')
    signature = data.get('signature')

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401

    # Verify signature
    try:
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        razorpay_client.utility.verify_payment_signature(params_dict)

        # Save to DB
        new_payment = Payment(
            user_id=user_id,
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
            status="Paid"
        )
        db.session.add(new_payment)

        # Update Order status
        order = Order.query.filter_by(razorpay_order_id=order_id).first()
        if order:
            order.status = "Paid"
        db.session.commit()

        return jsonify({'message': 'Payment successful'})
    except razorpay.errors.SignatureVerificationError:
        return jsonify({'error': 'Payment verification failed'}), 400

@app.route('/routes', methods=['GET'])
def list_routes():
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        line = urllib.parse.unquote(f"{rule.endpoint}: {methods} {rule}")
        output.append(line)
    return "<br>".join(sorted(output))

# ✅ Run Flask
if __name__ == '__main__':
    app.run(debug=True)



