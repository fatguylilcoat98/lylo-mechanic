"""
LYLO Mechanic — Auth Middleware
The Good Neighbor Guard · Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

Verifies Supabase JWT tokens on protected endpoints.
"""

import os
import logging
from functools import wraps
from flask import request, jsonify, g
import jwt

logger = logging.getLogger("lylo.auth")

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Endpoints that require authentication
PROTECTED_PREFIXES = (
    "/api/v1/diagnose",
    "/api/v1/quick",
    "/api/v1/billing",
    "/api/v1/analyze",
)


def verify_token(token: str) -> dict | None:
    """Verify a Supabase JWT and return the payload, or None if invalid."""
    if not SUPABASE_JWT_SECRET:
        logger.warning("SUPABASE_JWT_SECRET not set — skipping token verification")
        return {"sub": "anonymous", "email": ""}

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        return None


def get_user_id_from_request() -> str:
    """
    Extract user ID from request.
    Priority: JWT sub claim > IP address fallback
    """
    user = getattr(g, "current_user", None)
    if user and user.get("sub"):
        return user["sub"]
    # Fallback to IP for unauthenticated endpoints
    return request.remote_addr or "unknown"


def require_auth(f):
    """Decorator to require valid JWT on a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({
                "error": "Authentication required",
                "code": "MISSING_TOKEN",
                "message": "Please log in to use this feature."
            }), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_token(token)

        if payload is None:
            return jsonify({
                "error": "Invalid or expired token",
                "code": "INVALID_TOKEN",
                "message": "Your session has expired. Please log in again."
            }), 401

        g.current_user = payload
        g.user_id = payload.get("sub", request.remote_addr)
        return f(*args, **kwargs)
    return decorated


def init_auth(app):
    """
    Register auth middleware on the Flask app.
    Protects all PROTECTED_PREFIXES automatically.
    """
    @app.before_request
    def _check_auth():
        # Only protect specific prefixes
        if not any(request.path.startswith(p) for p in PROTECTED_PREFIXES):
            return None  # Not a protected route, let it through

        # OPTIONS requests skip auth (CORS preflight)
        if request.method == "OPTIONS":
            return None

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({
                "error": "Authentication required",
                "code": "MISSING_TOKEN",
                "message": "Please log in to use this feature."
            }), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_token(token)

        if payload is None:
            return jsonify({
                "error": "Invalid or expired token",
                "code": "INVALID_TOKEN",
                "message": "Your session has expired. Please log in again."
            }), 401

        # Store user info on g for use in route handlers
        g.current_user = payload
        g.user_id = payload.get("sub", request.remote_addr)
        logger.info("AUTH OK user_id=%s path=%s", g.user_id, request.path)
        return None  # Continue to route handler
