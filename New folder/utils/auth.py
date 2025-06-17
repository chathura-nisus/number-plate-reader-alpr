# anpr_flask_project/utils/auth.py
import jwt
from functools import wraps
from flask import request, jsonify


class JWTManager:
    """Manages JWT token validation for Flask routes."""

    def __init__(self, app=None, odoo_connector=None, logging_service=None):
        self.app = app
        self.odoo_connector = odoo_connector
        self.logger = logging_service
        self.jwt_secret = None

    def init_app(self, app, odoo_connector, logging_service):
        """Binds the manager to the Flask app and other components."""
        self.app = app
        self.odoo_connector = odoo_connector
        self.logger = logging_service

        # Fetch the secret on initialization
        if self.odoo_connector:
            self.jwt_secret = self.odoo_connector.anpr_settings.get('jwt_secret')

        if not self.jwt_secret:
            self.logger.web_log("JWT secret key is NOT configured in Odoo. API endpoints will be insecure.", "critical")
        else:
            self.logger.web_log("JWT secret loaded from Odoo. API endpoints are protected.", "info")

    def jwt_required(self, f):
        """A decorator to protect routes with JWT authentication."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = None
            auth_header = request.headers.get('Authorization')

            if auth_header:
                parts = auth_header.split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]

            if not token:
                return jsonify({'status': 'error', 'message': 'Authorization token is missing!'}), 401

            if not self.jwt_secret:
                self.logger.web_log("Rejected API call because JWT secret is not configured on the server.", "error")
                return jsonify({'status': 'error', 'message': 'Server authentication is not configured!'}), 500

            try:
                # Decode the token to validate it
                jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return jsonify({'status': 'error', 'message': 'Token has expired!'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'status': 'error', 'message': 'Token is invalid!'}), 401

            # Token is valid, proceed with the original function
            return f(*args, **kwargs)

        return decorated_function


# Create a global instance to be imported by other modules
jwt_manager = JWTManager()
