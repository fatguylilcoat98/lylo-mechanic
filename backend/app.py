"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

app.py — Main Flask application with auth, credits, billing, and rate limiting
"""

import os
import re
import json
import time
import uuid
import threading
from datetime import datetime, timezone
from collections import defaultdict
from threading import Lock

from flask import Flask, render_template, request, jsonify, make_response, session
from engine import Veracore
from models import db, seed_plans, Investigation, AuditEvent, DecisionPacket, VALID_HUMAN_DECISIONS
from auth import auth_bp, _current_user, require_login
from billing import billing_bp
from admin import admin_bp
from credits import check_credits, deduct_credit, log_investigation
from care_layer import build_care_layer

# ── APP SETUP ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///veracore.db")
# Render gives postgres:// — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"]        = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_SECURE"]          = True
app.config["SESSION_COOKIE_HTTPONLY"]        = True
app.config["SESSION_COOKIE_SAMESITE"]        = "Lax"

db.init_app(app)

# Ensure all tables exist on startup (including new models like DecisionPacket)
# Authored by Devin-Agent [EBL-1]
# Modified by Devin-Agent [EBL-2] — safe migration for Phase 2 columns + indexes
# Modified by Devin-Agent [EBL-2-hotfix] — moved to background thread so gunicorn
# can bind to $PORT immediately. Render's port-scan was timing out because the
# synchronous db.create_all() + migration blocked module-level import.
def _run_startup_migration():
    """Background: create tables + run EBL-2 migrations. Pure fire-and-forget."""
    try:
        with app.app_context():
            print("[EBL] db.create_all() starting...")
            try:
                db.create_all()
                # EBL Phase 2: safe migration — add new columns if they don't exist
                # Uses ADD COLUMN IF NOT EXISTS so existing rows are unaffected.
                # Authored by Devin-Agent [EBL-2]
                from sqlalchemy import text as sa_text, inspect as sa_inspect
                _ebl2_migrations = [
                    "ALTER TABLE decision_packets ADD COLUMN IF NOT EXISTS modified_answer TEXT",
                    "ALTER TABLE decision_packets ADD COLUMN IF NOT EXISTS decision_timestamp TIMESTAMPTZ",
                ]
                _ebl2_indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_dp_timestamp  ON decision_packets (timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_dp_session_id ON decision_packets (session_id)",
                    "CREATE INDEX IF NOT EXISTS idx_dp_version_id ON decision_packets (version_id)",
                ]
                for stmt in _ebl2_migrations + _ebl2_indexes:
                    try:
                        db.session.execute(sa_text(stmt))
                    except Exception as mig_err:
                        print(f"[EBL-2] migration skipped: {mig_err}")
                db.session.commit()
                # Verify
                inspector = sa_inspect(db.engine)
                tables = inspector.get_table_names()
                if "decision_packets" in tables:
                    cols = [c["name"] for c in inspector.get_columns("decision_packets")]
                    print(f"[EBL] ✓ decision_packets EXISTS — columns: {cols}")
                else:
                    print("[EBL] ✗ decision_packets NOT FOUND")
            except Exception as e:
                print(f"[EBL] ✗ db.create_all() FAILED: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        print(f"[EBL] ✗ startup migration outer error: {e}")

threading.Thread(target=_run_startup_migration, daemon=True).start()

# Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(admin_bp)

# Engine (lazy init)
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = Veracore()
    return _engine

# ── CONFIG ────────────────────────────────────────────────────────────────────

INPUT_MAX_CHARS          = int(os.getenv("INPUT_MAX_CHARS", "250"))
MAX_DAILY_INVESTIGATIONS = int(os.getenv("MAX_DAILY_INVESTIGATIONS", "2000"))
RATE_LIMIT_PER_MIN       = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))   # per user per minute

# ── CORS ──────────────────────────────────────────────────────────────────────

ALLOWED_ORIGINS = {
    "https://thegoodneighborguard.com",
    "https://www.thegoodneighborguard.com",
    "https://veracore.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://fatguylilcoat98.github.io",
}

def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"]  = origin
        response.headers["Vary"]                         = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.after_request
def apply_cors(response):
    return add_cors_headers(response)

def cors_preflight():
    r = make_response("", 204)
    return add_cors_headers(r)

def get_client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"

# ── DAILY GUARDRAIL ───────────────────────────────────────────────────────────

_daily_lock  = Lock()
_daily_count = {"date": None, "count": 0}

def _daily_ok():
    today = datetime.now(timezone.utc).date().isoformat()
    with _daily_lock:
        if _daily_count["date"] != today:
            _daily_count["date"]  = today
            _daily_count["count"] = 0
        if _daily_count["count"] >= MAX_DAILY_INVESTIGATIONS:
            return False
        _daily_count["count"] += 1
    return True

# ── PER-USER RATE LIMITER ─────────────────────────────────────────────────────

_rate_lock    = Lock()
_rate_windows = defaultdict(list)   # user_id → [timestamps]

def _rate_ok(user_id):
    now = time.time()
    window_start = now - 60
    with _rate_lock:
        hits = _rate_windows[user_id]
        hits[:] = [t for t in hits if t > window_start]
        if len(hits) >= RATE_LIMIT_PER_MIN:
            return False
        hits.append(now)
    return True

# ── NORMALIZATION ─────────────────────────────────────────────────────────────

def _safe_str(v):
    if isinstance(v, str):  return v.strip()
    if isinstance(v, dict): return " ".join(str(x) for x in v.values() if x).strip()
    if isinstance(v, list): return " ".join(str(x) for x in v if x).strip()
    if v is None:           return ""
    return str(v).strip()

def _safe_int(v, default=None):
    if v is None: return default
    try:    return max(0, int(float(v)))
    except: return default

def _safe_float(v, default=None):
    if v is None: return default
    try:    return float(v)
    except: return default

def _extract_answer(raw):
    if isinstance(raw, str): return raw
    if not isinstance(raw, dict): return _safe_str(raw) or "Verification completed."
    final = raw.get("final") or {}
    for key in ("answer", "final_answer", "response", "text"):
        val = _safe_str(final.get(key))
        if val and len(val) > 10: return val
    for key in ("answer", "final_answer", "response", "text"):
        val = _safe_str(raw.get(key))
        if val and len(val) > 10: return val
    return "Verification completed."

def _extract_confidence(raw):
    if not isinstance(raw, dict): return None
    final = raw.get("final") or {}
    for src in (final, raw):
        for key in ("confidence_score", "confidence", "score"):
            v = _safe_int(src.get(key))
            if v is not None: return max(0, min(100, v))
    return None

def _extract_verdict(raw):
    if not isinstance(raw, dict): return None
    final = raw.get("final") or {}
    for src in (final, raw):
        for key in ("confidence_label", "verdict", "label", "result_label", "signal", "confidence_color"):
            val = _safe_str(src.get(key))
            if val: return val
    return None

def _extract_risk_tier(raw):
    if not isinstance(raw, dict): return None
    final = raw.get("final") or {}
    for src in (final, raw):
        v = _safe_int(src.get("risk_tier"))
        if v is not None: return v
    return None

def _confidence_to_agreement(confidence, verdict):
    """
    Converts a confidence score or verdict string into an agreement level.
    Thresholds calibrated to avoid under-reporting consensus on well-evidenced claims.
    """
    if isinstance(confidence, int):
        if confidence >= 65: return "strong"
        if confidence >= 45: return "moderate"
        if confidence >= 25: return "mixed"
        return "conflict"
    if verdict:
        v = verdict.lower()
        if any(w in v for w in ("high confidence", "verified", "true", "confirmed", "strong")): return "strong"
        if any(w in v for w in ("moderate", "likely")):                                         return "moderate"
        if any(w in v for w in ("mixed", "uncertain", "caution", "yellow")):                    return "mixed"
        if any(w in v for w in ("false", "conflict", "red", "low confidence")):                 return "conflict"
    return "strong"

def _extract_models_run(raw):
    if not isinstance(raw, dict): return []
    stages     = raw.get("stages") or {}
    generation = stages.get("generation") or []
    trace      = []
    if isinstance(raw.get("final"), dict):
        trace = raw["final"].get("trace") or []

    MODEL_ID_MAP = {
        "claude": "claude", "sonnet": "claude", "claudesonnet": "claude", "claude3": "claude",
        "gpt": "gpt", "gpt4": "gpt", "gpt-4": "gpt", "openai": "gpt",
        "groq": "groq", "groq-llama": "groq", "llama": "groq",
        "gemini": "gemini", "gemini-flash": "gemini", "gemini2": "gemini",
        "claudeopus": "opus", "opus": "opus",
    }
    seen_ids = {}
    for entry in generation:
        if not isinstance(entry, dict): continue
        raw_name = _safe_str(entry.get("model") or entry.get("name") or "")
        role     = _safe_str(entry.get("role") or "retrieval")
        dur      = _safe_int(entry.get("duration_ms"))
        answer   = _safe_str(entry.get("answer") or "")
        key      = re.sub(r"[\s\-_]", "", raw_name.lower())
        ui_id    = None
        for pattern, mapped in MODEL_ID_MAP.items():
            if pattern in key: ui_id = mapped; break
        if ui_id is None: ui_id = key[:12] if key else "unknown"
        status = "complete" if (answer and len(answer) > 10) else (
            "timeout" if "timeout" in _safe_str(entry.get("limitations")).lower() else "error"
        )
        if ui_id in seen_ids:
            existing = seen_ids[ui_id]
            if status == "complete": existing["status"] = "complete"
            existing["roles"].add(role)
            if dur and dur > (existing["duration_ms"] or 0): existing["duration_ms"] = dur
        else:
            seen_ids[ui_id] = {"id": ui_id, "name": raw_name or ui_id.capitalize(),
                               "roles": {role}, "status": status, "duration_ms": dur}

    for t_entry in trace:
        if not isinstance(t_entry, dict): continue
        stage = _safe_str(t_entry.get("stage")).lower()
        if "opus" in stage and t_entry.get("status") == "done" and "opus" not in seen_ids:
            seen_ids["opus"] = {"id": "opus", "name": "Claude Opus",
                                "roles": {"adversarial"}, "status": "complete", "duration_ms": None}

    return [{"id": e["id"], "name": e["name"], "role": list(e["roles"]),
             "status": e["status"], "duration_ms": e["duration_ms"]} for e in seen_ids.values()]

def _opus_engaged(raw, models_run):
    if any(m["id"] == "opus" for m in models_run): return True
    if isinstance(raw, dict):
        final = raw.get("final") or {}
        trace = final.get("trace") or []
        for t in trace:
            if not isinstance(t, dict): continue
            if "opus" in _safe_str(t.get("stage")).lower() and t.get("status") == "done":
                return True
    return False

def _extract_sources(raw):
    if not isinstance(raw, dict): return [], 0
    final  = raw.get("final") or {}
    stages = raw.get("stages") or {}
    raw_sources = final.get("all_sources") or raw.get("all_sources") or []
    if not raw_sources:
        for entry in (stages.get("generation") or []):
            if isinstance(entry, dict): raw_sources.extend(entry.get("sources") or [])
    normalized = []
    seen_urls  = set()
    for s in raw_sources:
        if not isinstance(s, dict): continue
        url    = _safe_str(s.get("url_or_reference") or s.get("url") or s.get("link") or "")
        title  = _safe_str(s.get("name") or s.get("title") or s.get("source_name") or "")
        domain = _safe_str(s.get("domain") or "")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not domain and url:
            m = re.match(r"https?://(?:www\.)?([^/]+)", url)
            if m: domain = m.group(1)
        if not title and domain: title = domain
        if not title and url:    title = url[:60]
        if not title: continue
        url_key = url or title
        if url_key in seen_urls: continue
        seen_urls.add(url_key)
        normalized.append({"title": title, "url": url, "domain": domain})
    total = _safe_int(final.get("total_unique_sources")) or _safe_int(raw.get("total_unique_sources")) or len(normalized)
    return normalized, total

def _extract_safety(raw):
    if not isinstance(raw, dict): return True, None
    final = raw.get("final") or {}
    mode  = _safe_str(final.get("verification_mode") or raw.get("verification_mode") or "")
    if "INJECTION_BLOCKED" in mode.upper():
        return False, "This question was flagged by the security layer and could not be processed."
    injection_flag = raw.get("injection_blocked") or final.get("injection_blocked")
    if injection_flag is True:
        answer = _safe_str(final.get("answer") or raw.get("answer") or "")
        if len(answer) < 5:
            return False, "This question was flagged for security reasons and could not be answered."
    return True, None

def _extract_more_info(raw):
    if not isinstance(raw, dict): return None
    final = raw.get("final") or {}
    adv   = final.get("adversarial_challenges") or {}
    pieces = []
    assumptions = adv.get("hidden_assumptions") or []
    if assumptions:
        pieces.append("Hidden assumptions identified: " + "; ".join(_safe_str(a) for a in assumptions[:3] if a))
    counter = adv.get("counterexamples") or []
    if counter:
        pieces.append("Alternative perspectives: " + "; ".join(_safe_str(c) for c in counter[:2] if c))
    note = _safe_str(final.get("disagreement_note"))
    if note: pieces.append(note)
    cv = final.get("compound_verdict")
    if isinstance(cv, dict):
        sub = _safe_str(cv.get("summary") or cv.get("verdict_summary") or "")
        if sub: pieces.append("Detailed breakdown: " + sub)
    return "\n\n".join(pieces) if pieces else None

def _extract_verification_mode(raw):
    if not isinstance(raw, dict): return "Pipeline"
    final = raw.get("final") or {}
    mode  = _safe_str(final.get("verification_mode") or raw.get("verification_mode") or "")
    MAP = {
        "DETERMINISTIC_ONLY":     "Deterministic Match",
        "DETERMINISTIC_OVERRIDE": "Deterministic Override",
        "TIER_1_FAST":            "Fast Lookup (Tier 1)",
        "TIER_2_SOURCED":         "Sourced Lookup (Tier 2)",
        "TIER_3_CROSS_EVAL":      "Cross-Evaluated (Tier 3)",
        "TIER_4_FULL_PIPELINE":   "Full Investigation (Tier 4)",
        "TIER_5_FULL_PIPELINE":   "Full Investigation + Opus (Tier 5)",
        "GLOBAL_TIMEOUT":         "Partial — Timeout",
        "ERROR_FALLBACK":         "Error Recovery",
        "INJECTION_BLOCKED":      "Security Block",
    }
    for key, label in MAP.items():
        if key in mode.upper(): return label
    return mode.replace("_", " ").title() if mode else "Pipeline"

def _extract_classification(raw):
    """Extract classification metadata from engine stages for care layer."""
    if not isinstance(raw, dict): return None
    stages = raw.get("stages") or {}
    cl = stages.get("classification")
    if isinstance(cl, dict):
        return cl
    return None

def normalize_result(raw, question, elapsed_ms):
    answer     = _extract_answer(raw)
    confidence = _extract_confidence(raw)
    verdict    = _extract_verdict(raw)
    risk_tier  = _extract_risk_tier(raw)
    models_run = _extract_models_run(raw)
    opus_ran   = _opus_engaged(raw, models_run)
    sources, total_sources = _extract_sources(raw)
    instruction_allowed, safety_notice = _extract_safety(raw)
    more_info  = _extract_more_info(raw)
    agreement  = _confidence_to_agreement(confidence, verdict)
    mode       = _extract_verification_mode(raw)
    return {
        "ok":                   True,
        "question":             question,
        "answer":               answer,
        "verdict":              verdict,
        "confidence_score":     confidence,
        "agreement_level":      agreement,
        "risk_tier":            risk_tier,
        "verification_mode":    mode,
        "models_run":           models_run,
        "opus_engaged":         opus_ran,
        "sources":              sources,
        "total_unique_sources": total_sources,
        "instruction_allowed":  instruction_allowed,
        "safety_notice":        safety_notice,
        "more_info":            more_info,
        "elapsed_ms":           elapsed_ms,
        "classification":       _extract_classification(raw),
    }

# ── PAGES ─────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/account")
@require_login
def account():
    user = _current_user()
    return render_template("account.html", user=user)

# ── STAGE: Cora Voice UI ─────────────────────────────────────────────────
# Authored/Modified by Devin-Agent [TRIAL-001]
# Serves the Cora voice interface at /stage for staging and demo access.
# Supports the Veracore Constitution: Truth > Speed, Human Tone, The Handshake.
# This route makes Cora's UI accessible from the Render backend without
# needing a separate static hosting deployment.

@app.route("/stage")
def stage():
    return render_template("stage.html")

# ── API: STATUS ───────────────────────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"ok": True, "service": "Veracore", "version": "2.0", "status": "online"})

# ── API: ME ───────────────────────────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
def me():
    user = _current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    plan = user.plan
    return jsonify({
        "ok": True,
        "user": {
            "id":                user.id,
            "email":             user.email,
            "account_type":      user.account_type,
            "credits_remaining": user.credits_remaining,
            "credits_used":      user.credits_used,
            "credit_limit":      user.credit_limit,
            "plan": {
                "name":         plan.name if plan else "Free",
                "account_type": plan.account_type if plan else "individual",
            } if plan else {"name": "Free", "account_type": "individual"},
            "organization": {
                "name": user.organization.name,
            } if user.is_org_member and user.organization else None,
        }
    })

# ── DECISION PACKET CAPTURE (EBL Phase 1) ────────────────────────────────────
# Authored by Devin-Agent [EBL-1]
# Fire-and-forget background capture of every verified answer.
# Uses a daemon thread so the main response path never waits for the DB write.
# Supports the Veracore Constitution:
#   - Traceability (Principle 15): every answer is recorded and traceable
#   - Human-in-the-loop (Principle 4): packets await human review (human_decision=null)
#   - Errors trigger learning (Principle 19): captured data enables post-hoc analysis

def _capture_packet(packet_data):
    """Insert a DecisionPacket in a background thread. Never crashes the main response."""
    try:
        with app.app_context():
            try:
                pkt = DecisionPacket(
                    version_id       = packet_data["version_id"],
                    session_id       = packet_data.get("session_id"),
                    question         = packet_data["question"],
                    answer           = packet_data["answer"],
                    confidence_score = packet_data.get("confidence_score"),
                    sources_json     = json.dumps(packet_data.get("sources", [])),
                    human_decision   = None,
                    human_reason     = None,
                )
                db.session.add(pkt)
                db.session.commit()
            except Exception:
                db.session.rollback()  # clean up failed transaction while context is active
    except Exception:
        pass  # never crash the main response


def _fire_decision_packet(result, session_id=None):
    """Build packet data from a normalized result and fire background capture.
    Returns the version_id so it can be included in the API response.
    # Modified by Devin-Agent [EBL-3] — return version_id for frontend decision buttons
    """
    vid = str(uuid.uuid4())
    packet_data = {
        "version_id":       vid,
        "session_id":       session_id,
        "question":         result.get("question", ""),
        "answer":           result.get("answer", ""),
        "confidence_score": result.get("confidence_score"),
        "sources":          result.get("sources", []),
    }
    threading.Thread(target=_capture_packet, args=(packet_data,), daemon=True).start()
    return vid


# ── API: ASK (public) ─────────────────────────────────────────────────────────

@app.route("/ask", methods=["POST", "OPTIONS"])
def ask_public():
    if request.method == "OPTIONS":
        return cors_preflight()
    client_ip = get_client_ip()
    if not _rate_ok(client_ip):
        return jsonify({"ok": False, "error": "Too many requests."}), 429
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "Question is required."}), 400
    if len(question) > INPUT_MAX_CHARS:
        return jsonify({"ok": False, "error": f"Questions are limited to {INPUT_MAX_CHARS} characters."}), 400
    try:
        vc = get_engine()
        raw = vc.run(question)
        elapsed = round((time.time() - t0) * 1000)
        result = normalize_result(raw, question, elapsed)
        # Care Layer v1 — decision boundary
        result["care_layer"] = build_care_layer(
            result=result,
            classification=result.get("classification"),
        )
        # EBL Phase 1: fire-and-forget decision packet capture — Devin-Agent [EBL-1]
        # Modified by Devin-Agent [EBL-3] — include version_id for decision buttons
        result["version_id"] = _fire_decision_packet(result)
        return jsonify(result)
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        return jsonify({"ok": False, "error": str(e), "elapsed_ms": elapsed}), 500


# ── API: ASK (protected) ──────────────────────────────────────────────────────

@app.route("/api/ask", methods=["POST", "OPTIONS"])
def ask():
    if request.method == "OPTIONS":
        return cors_preflight()

    # ── 1. Auth ──
    user = _current_user()
    if not user:
        return jsonify({
            "ok":    False,
            "error": "Login required to run an investigation.",
            "code":  "LOGIN_REQUIRED",
        }), 401

    # ── 2. Per-user rate limit ──
    if not _rate_ok(user.id):
        return jsonify({
            "ok":    False,
            "error": f"Too many requests. Limit is {RATE_LIMIT_PER_MIN} investigations per minute.",
            "code":  "RATE_LIMITED",
        }), 429

    # ── 3. Daily system guardrail ──
    if not _daily_ok():
        return jsonify({
            "ok":    False,
            "error": "Veracore is experiencing high demand. Please try again in a few hours.",
            "code":  "DAILY_CAP",
        }), 503

    # ── 4. Credit check ──
    credits_ok, credit_error = check_credits(user)
    if not credits_ok:
        return credit_error

    # ── 5. Validate question ──
    t0       = time.time()
    data     = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "Question is required.", "elapsed_ms": 0}), 400
    if len(question) > INPUT_MAX_CHARS:
        return jsonify({
            "ok":      False,
            "error":   f"Questions are limited to {INPUT_MAX_CHARS} characters.",
            "elapsed_ms": 0,
        }), 400

    # ── 6. Run pipeline ──
    try:
        vc      = get_engine()
        raw     = vc.run(question)
        elapsed = round((time.time() - t0) * 1000)
        result  = normalize_result(raw, question, elapsed)

        # Care Layer v1 — decision boundary
        result["care_layer"] = build_care_layer(
            result=result,
            classification=result.get("classification"),
        )

        # ── 7. Deduct credit + log ──
        deduct_credit(user)
        log_investigation(user, question, result, elapsed)

        # ── 8. Append usage info to response ──
        result["credits_remaining"] = user.credits_remaining

        # EBL Phase 1: fire-and-forget decision packet capture — Devin-Agent [EBL-1]
        # Modified by Devin-Agent [EBL-3] — include version_id for decision buttons
        result["version_id"] = _fire_decision_packet(result, session_id=str(user.id))

        return jsonify(result)

    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        return jsonify({
            "ok":         False,
            "error":      f"Verification engine failed: {str(e)}",
            "elapsed_ms": elapsed,
        }), 500


# ── API: DECISION (EBL Phase 2) ──────────────────────────────────────────────
# Authored by Devin-Agent [EBL-2]
# Records a human decision against an existing Decision Packet.
# Supports the Veracore Constitution:
#   - The human stays in the loop (Principle 4)
#   - Traceability (Principle 15): decisions are recorded and traceable
#   - Errors trigger learning (Principle 19): human corrections feed the learning loop

@app.route("/api/decision", methods=["POST", "OPTIONS"])
@require_login
def record_decision():
    if request.method == "OPTIONS":
        return cors_preflight()

    data = request.get_json(silent=True) or {}

    # ── Validate version_id ──
    version_id = (data.get("version_id") or "").strip()
    if not version_id:
        return jsonify({"ok": False, "error": "version_id is required."}), 400

    # ── Validate human_decision ──
    human_decision = (data.get("human_decision") or "").strip().lower()
    if human_decision not in VALID_HUMAN_DECISIONS:
        return jsonify({
            "ok":    False,
            "error": f"human_decision must be one of: {', '.join(sorted(VALID_HUMAN_DECISIONS))}",
        }), 400

    # ── Validate modified_answer when decision is 'modified' ──
    modified_answer = (data.get("modified_answer") or "").strip() or None
    if human_decision == "modified" and not modified_answer:
        return jsonify({
            "ok":    False,
            "error": "modified_answer is required when human_decision is 'modified'.",
        }), 400

    human_reason = (data.get("human_reason") or "").strip() or None

    # ── Look up the packet ──
    pkt = DecisionPacket.query.filter_by(version_id=version_id).first()
    if not pkt:
        return jsonify({"ok": False, "error": "Decision packet not found."}), 404

    # ── Record the decision ──
    pkt.human_decision     = human_decision
    pkt.human_reason       = human_reason
    pkt.modified_answer    = modified_answer if human_decision == "modified" else None
    pkt.decision_timestamp = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Failed to save decision."}), 500

    return jsonify({"ok": True, "version_id": version_id})


# ── DATABASE INIT ─────────────────────────────────────────────────────────────

@app.cli.command("init-db")
def init_db():
    """Create all tables and seed plan data."""
    with app.app_context():
        db.create_all()
        seed_plans()
        print("✓ Database initialized and plans seeded.")


@app.cli.command("create-admin")
def create_admin():
    """Create an admin user interactively."""
    import getpass
    from models import User, Plan
    from werkzeug.security import generate_password_hash

    email    = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password: ")

    existing = User.query.filter_by(email=email).first()
    if existing:
        existing.role = "admin"
        db.session.commit()
        print(f"✓ Existing user {email} promoted to admin.")
        return

    free_plan = Plan.query.filter_by(name="Free").first()
    user = User(
        email         = email,
        password_hash = generate_password_hash(password),
        account_type  = "individual",
        role          = "admin",
        plan_id       = free_plan.id if free_plan else None,
        credit_limit  = 9999,
        credits_used  = 0,
    )
    db.session.add(user)
    db.session.commit()
    print(f"✓ Admin user {email} created.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
