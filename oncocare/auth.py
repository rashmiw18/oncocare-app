"""
OncoCare AI — Auth helpers
============================
Simple session-based authentication (Flask's signed-cookie session — no
extra dependency). Passwords hashed with werkzeug's generate/check_password_hash.
"""

from functools import wraps
from flask import session, redirect, url_for, request, jsonify
import db


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.get_user_by_id(uid)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Not authenticated"}), 401
                return redirect(url_for("login"))
            if session.get("role") != role:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Forbidden"}), 403
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator
