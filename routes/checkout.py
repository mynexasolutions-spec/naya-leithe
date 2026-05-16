from flask import Blueprint

checkout_bp = Blueprint('checkout', __name__)

# Checkout logic has been moved to cart.py to share cart session context seamlessly.
