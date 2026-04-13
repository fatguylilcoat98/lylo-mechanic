"""
Supabase JWT authentication for LYLO Mechanic.

Verifies Supabase-issued access tokens using the project's shared JWT secret
(HS256). On success, sets g.user_id and g.user_email for the duration of the
request. On failure, returns 401 with a machine-readable reason code.

Env vars:
    SUPABASE_JWT_SECRET — from Supabase dashboard →
        Project Settings → API → JWT Settings → "JWT Secret"

Usage:
    from auth.supabase_auth import require_auth

    @my_bp.route("/protected", methods=["POST"])
    @require_auth
    def handler():
        return jsonify({"user_id": g.user_id})
"""

import logging
import os
from functools import wraps

import jwt
from flask import g, jsonify, request

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_JWT_AUDIENCE = "authenticated"
SUPABASE_JWT_ALGO = "HS256"


def _unauthorized(reason: str, status: int = 401):
    logger.warning("AUTH REJECTED: reason=%s path=%s", reason, request.path)
    return jsonify({"error": "unauthorized", "reason": reason}), status


def require_auth(fn):
    """Route decorator that verifies a Supabase Bearer JWT.

    Sets on flask.g before calling the wrapped function:
        g.user_id     — Supabase auth UUID (from `sub` claim)
        g.user_email  — email from `email` claim, or "" if absent
        g.user_claims — full decoded claim dict
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not SUPABASE_JWT_SECRET:
            logger.error("SUPABASE_JWT_SECRET is not set — cannot verify tokens")
            return jsonify({
                "error": "server_misconfigured",
                "reason": "SUPABASE_JWT_SECRET not set on server",
            }), 500

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("missing_bearer_token")

        token = auth_header[7:].strip()
        if not token:
            return _unauthorized("empty_token")

        try:
            claims = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=[SUPABASE_JWT_ALGO],
                audience=SUPABASE_JWT_AUDIENCE,
            )
        except jwt.ExpiredSignatureError:
            return _unauthorized("token_expired")
        except jwt.InvalidAudienceError:
            return _unauthorized("invalid_audience")
        except jwt.InvalidSignatureError:
            return _unauthorized("invalid_signature")
        except jwt.InvalidTokenError as e:
            return _unauthorized(f"invalid_token: {e}")

        sub = claims.get("sub")
        if not sub:
            return _unauthorized("token_missing_sub")

        g.user_id = sub
        g.user_email = claims.get("email", "")
        g.user_claims = claims

        logger.info("AUTH OK user_id=%s path=%s", sub, request.path)
        return fn(*args, **kwargs)

    return wrapper
