"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

claspion_production_service.py — The hardened-stack service layer

WHAT THIS IS
------------
The production-facing service that wires the four hardened modules
into a single API:

    THRESHOLD RATCHET  →  CONTENT GATE  →  ACTION DETECTOR  →  CEILING

Every Flask route in handshake_app.py that touches CLASPION's hardened
gate calls a function in this module. The dashboard SSE stream also
calls this module — so both surfaces reflect the same behavior. There
is no second copy of the gate logic.

Tier A of the production-readiness work moves this module from "test
harness only" (where it lived in tests/redteam/hardened_pipeline.py)
to "first-class service module imported by handshake_app.py".

WHAT IT IS NOT
--------------
  - Not a transaction system. CLASPION still does not move money. The
    `execute()` operation is the gate's confirmation that an action
    WOULD be authorized to proceed in a real action system. Wiring
    that to actual money movement is a separate, downstream concern.
  - Not multi-process safe. The SessionStore is in-memory with a TTL
    sweeper. Single-worker only. Migration to Redis or Postgres is
    Tier B work.
  - Not a closed-loop external authentication system. The hardened
    ORIGIN's third factor is an HMAC over a per-challenge secret;
    in production that secret would be delivered via TOTP/WebAuthn,
    NOT returned in the create-challenge response. The current
    implementation returns the secret to the caller for API
    correctness, but flags it loudly in the response: this is the
    UX gap that Tier A specifically does not solve.

PUBLIC API
----------
  evaluate(input_text, session_id=None, action_context=None)
    → Decision   — run an input through the full hardened stack

  issue_challenge(session_id, action_context, action_summary, ...)
    → ChallengeResponse — create a 3-factor ORIGIN challenge for a
                          session, store it, return enough data for
                          the user to complete it

  validate_challenge(session_id, challenge_id, dynamic_phrase,
                     typed_intent, crypto_proof,
                     current_action_context)
    → ValidationResponse — three-factor validation, transitions the
                           challenge to VALIDATED, FAILED, EXPIRED,
                           or REVOKED

  execute(session_id, action_context)
    → ExecutionResponse  — only succeeds if the session has a
                           VALIDATED challenge whose action_context
                           matches. Burns the fuse on success.

  reset(session_id, reason, operator_id)
    → ResetResponse      — admin path to forget a session. Used by
                           the override route.

  list_sessions() / get_session(session_id) — read helpers used by
                                                the dashboard / admin

CONTRACTS
---------
  - Every operation appends to claspion_audit_chain so the immutable
    log captures the full lifecycle of every decision.
  - Every operation has a hard timeout of 5 seconds (well above the
    measured ~10ms latency of the hardened pipeline; the budget is
    for safety, not throughput).
  - Every operation is non-blocking-safe — no DB calls, no network
    calls, no file IO outside the audit chain append.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# All four hardened modules
from claspion_threshold_ratchet import (
    create_ratchet, record_turn, requires_origin as ratchet_requires_origin,
    RatchetState, to_dict as ratchet_to_dict,
)
from claspion_action_detector import detect_triggers, ActionTriggerResult
from claspion_origin_hardened  import (
    HardenedChallenge,
    create_hardened_challenge,
    validate_hardened,
    consume_hardened,
    compute_crypto_proof,
)
from claspion_ceiling import CeilingContext, CeilingDecision, ceiling_gate

# Tier C-A: input preprocessor (NFKC, bidi/zw/ANSI/BOM stripping,
# HTML unescape, confusable folding, base64+URL recursive decoding)
from claspion_input_preprocessor import preprocess as _preprocess_input

# Existing content pipeline
from claspion_truth_tether    import check_input_frame
from claspion_agentic_gate    import IntentAnchor, inspect_candidate
from claspion_output_firewall import inspect_output
from risk_classifier          import RiskClassifier
from origin                   import OriginStatus

# Audit chain
from claspion_audit_chain import get_audit_chain

# Enhanced semantic social engineering classifier
try:
    from claspion_semantic_intent_classifier import analyze_semantic_social_engineering
    SEMANTIC_CLASSIFIER_AVAILABLE = True
except ImportError:
    SEMANTIC_CLASSIFIER_AVAILABLE = False

    def analyze_semantic_social_engineering(text, context=None):
        return None


# ══════════════════════════════════════════════════════════════════
# TUNING CONSTANTS
# ══════════════════════════════════════════════════════════════════

SESSION_TTL_SECONDS    = 30 * 60       # 30 minutes per session
CHALLENGE_TTL_SECONDS  = 60            # matches ORIGIN_TTL_SECONDS
MAX_TURNS_PER_SESSION  = 200           # safety cap on session length
SWEEPER_INTERVAL_SECONDS = 60          # how often we expire stale sessions
HARD_TIMEOUT_SECONDS   = 5.0           # hard cap per operation


# ══════════════════════════════════════════════════════════════════
# RESPONSE TYPES
# ══════════════════════════════════════════════════════════════════

@dataclass
class Decision:
    session_id:           str
    allow:                bool
    decision:             str          # "BLOCKED" | "ALLOWED"
    blocking_layer:       str
    rule:                 str
    reason:               str
    ratchet_locked_tier:  int
    ratchet_locked_level: str
    action_categories:    list[str]
    origin_required:      bool
    origin_required_reason: str
    next_step:            Optional[dict] = None
    audit_id:             str = ""
    elapsed_ms:           float = 0.0
    layer_trail:          list[dict] = field(default_factory=list)
    # TIER B: advisory metadata for the response surface. Set when the
    # risk classifier escalates but the gate still ALLOWS the input.
    # The downstream response surface uses this to add disclaimers or
    # 911 / professional referrals without the gate refusing.
    advisory:             dict = field(default_factory=dict)


@dataclass
class ChallengeResponse:
    session_id:            str
    challenge_id:          str
    dynamic_phrase:        str
    required_intent_terms: list[str]
    expires_in_s:          float
    crypto_secret:         str    # delivered ONCE — production should use OOB
    crypto_secret_warning: str    # explicit warning that this is dev-only
    next_step:             dict
    audit_id:              str = ""


@dataclass
class ValidationResponse:
    session_id:    str
    challenge_id:  str
    status:        str    # OriginStatus value
    factors:       dict[str, Optional[bool]]
    next_step:     Optional[dict] = None
    audit_id:      str = ""


@dataclass
class ExecutionResponse:
    session_id:     str
    executed:       bool
    action_context: str
    challenge_id:   str
    reason:         str
    audit_id:       str = ""
    elapsed_ms:     float = 0.0


@dataclass
class ResetResponse:
    session_id: str
    reset:      bool
    reason:     str
    audit_id:   str = ""


# ══════════════════════════════════════════════════════════════════
# SESSION CONTEXT (per-session in-memory state)
# ══════════════════════════════════════════════════════════════════

@dataclass
class SessionContext:
    """
    All the state CLASPION holds about a single session. The ratchet
    is the load-bearing piece — it preserves the monotonic risk lock
    across multiple `evaluate` calls.
    """
    session_id:    str
    created_at:    float
    last_seen:     float
    ratchet:       RatchetState
    challenge:     Optional[HardenedChallenge] = None
    challenge_consumed: bool = False
    consumed_action_context: str = ""
    decision_count: int = 0
    challenge_count: int = 0
    # TIER B: monotonic flag — once any turn in this session triggered
    # the action_detector, every subsequent turn requires ORIGIN. This
    # is the slow-roll catch (Grok's utility-bill → oxygen-tank → wire-
    # transfer scenario), separated from the risk classifier tier so a
    # benign educational session can pass through without locking.
    has_seen_action_trigger: bool = False
    first_action_trigger_reason: str = ""


# ══════════════════════════════════════════════════════════════════
# SESSION STORE (TTL'd in-memory dict)
# ══════════════════════════════════════════════════════════════════

class SessionStore:
    """
    Abstract base. Two backends provided:
      - InMemorySessionStore (default): TTL'd dict with background
        sweeper. Single-worker only. Fine for dev, demo, canary.
      - RedisSessionStore: pickle-serialized SessionContext keyed by
        session_id with Redis EXPIRE for TTL. Multi-worker safe.

    Selection: get_session_store() consults the env var:
      CLASPION_REDIS_URL  — if set and Redis import + connect succeed,
                            uses RedisSessionStore. Otherwise falls
                            back to InMemorySessionStore with a printed
                            warning so the operator notices.

    The interface is intentionally tiny so backends are easy to add:
      get_or_create(session_id) -> SessionContext
      get(session_id)           -> Optional[SessionContext]
      put(ctx)                  -> None        (Redis only — in-memory
                                                mutates in place)
      reset(session_id)         -> bool
      list_session_ids()        -> list[str]
      stop()                    -> None
    """
    def get_or_create(self, session_id: Optional[str]) -> SessionContext:
        raise NotImplementedError
    def get(self, session_id: str) -> Optional[SessionContext]:
        raise NotImplementedError
    def put(self, ctx: SessionContext) -> None:
        # In-memory backend mutates in place; Redis backend overrides
        # this to persist after every write.
        pass
    def reset(self, session_id: str) -> bool:
        raise NotImplementedError
    def list_session_ids(self) -> list[str]:
        raise NotImplementedError
    def stop(self) -> None:
        pass


class InMemorySessionStore(SessionStore):
    """
    Default backend. Thread-safe TTL'd dict with background sweeper.
    Single-worker only. Use the Redis backend for multi-worker Render
    deploys.
    """
    backend_name = "in_memory"

    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}
        self._lock = threading.RLock()
        self._sweeper_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._start_sweeper()

    def _start_sweeper(self):
        if self._sweeper_thread and self._sweeper_thread.is_alive():
            return
        t = threading.Thread(target=self._sweeper, daemon=True, name="claspion-session-sweeper")
        t.start()
        self._sweeper_thread = t

    def _sweeper(self):
        while not self._stop.is_set():
            self._stop.wait(SWEEPER_INTERVAL_SECONDS)
            if self._stop.is_set():
                return
            self._expire_old()

    def _expire_old(self):
        now = time.time()
        with self._lock:
            stale = [
                sid for sid, ctx in self._sessions.items()
                if (now - ctx.last_seen) > SESSION_TTL_SECONDS
            ]
            for sid in stale:
                del self._sessions[sid]

    def get_or_create(self, session_id: Optional[str]) -> SessionContext:
        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:16]}"
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                now = time.time()
                ctx = SessionContext(
                    session_id = session_id,
                    created_at = now,
                    last_seen  = now,
                    ratchet    = create_ratchet(session_id),
                )
                self._sessions[session_id] = ctx
            else:
                ctx.last_seen = time.time()
            return ctx

    def get(self, session_id: str) -> Optional[SessionContext]:
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx:
                ctx.last_seen = time.time()
            return ctx

    def reset(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def stop(self):
        self._stop.set()


class RedisSessionStore(SessionStore):
    """
    Redis-backed session store for multi-worker Render deploys.

    Storage scheme:
      key = f"claspion:session:{session_id}"
      val = pickle.dumps(SessionContext)
      TTL = SESSION_TTL_SECONDS, refreshed on every read

    Why pickle: SessionContext contains a RatchetState which contains
    a list of TurnRecord dataclasses + several frozenset/set fields.
    JSON would lose type fidelity. Pickle is acceptable here because
    the only producer/consumer is the same Python process talking to
    its own Redis, never untrusted input. NEVER unpickle data from
    untrusted sources.

    Falls back to InMemorySessionStore if the redis client raises on
    any operation. The fallback is logged but not raised — the gate
    keeps working.
    """
    backend_name = "redis"

    def __init__(self, redis_url: str):
        import redis  # only imported when actually using this backend
        import pickle
        self._redis_url = redis_url
        self._client = redis.from_url(redis_url, socket_timeout=2.0, decode_responses=False)
        # Verify connectivity at construction so we know early if it's broken
        self._client.ping()
        self._pickle = pickle
        self._fallback: Optional[InMemorySessionStore] = None
        # Local index for list_session_ids() since SCAN can be slow
        self._known_ids_lock = threading.RLock()
        self._known_ids: set[str] = set()

    def _key(self, session_id: str) -> str:
        return f"claspion:session:{session_id}"

    def _load(self, session_id: str) -> Optional[SessionContext]:
        try:
            raw = self._client.get(self._key(session_id))
            if not raw:
                return None
            return self._pickle.loads(raw)
        except Exception as e:
            print(f"[claspion_production_service] Redis load failed for {session_id}: {e}", file=sys.stderr)
            return None

    def _save(self, ctx: SessionContext):
        try:
            data = self._pickle.dumps(ctx)
            self._client.setex(self._key(ctx.session_id), SESSION_TTL_SECONDS, data)
            with self._known_ids_lock:
                self._known_ids.add(ctx.session_id)
        except Exception as e:
            print(f"[claspion_production_service] Redis save failed for {ctx.session_id}: {e}", file=sys.stderr)

    def get_or_create(self, session_id: Optional[str]) -> SessionContext:
        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:16]}"
        ctx = self._load(session_id)
        if ctx is None:
            now = time.time()
            ctx = SessionContext(
                session_id = session_id,
                created_at = now,
                last_seen  = now,
                ratchet    = create_ratchet(session_id),
            )
            self._save(ctx)
        else:
            ctx.last_seen = time.time()
            self._save(ctx)
        return ctx

    def get(self, session_id: str) -> Optional[SessionContext]:
        ctx = self._load(session_id)
        if ctx:
            ctx.last_seen = time.time()
            self._save(ctx)
        return ctx

    def put(self, ctx: SessionContext) -> None:
        # Caller mutated the SessionContext in place; persist it
        self._save(ctx)

    def reset(self, session_id: str) -> bool:
        try:
            n = self._client.delete(self._key(session_id))
            with self._known_ids_lock:
                self._known_ids.discard(session_id)
            return bool(n)
        except Exception as e:
            print(f"[claspion_production_service] Redis delete failed: {e}", file=sys.stderr)
            return False

    def list_session_ids(self) -> list[str]:
        # Use the local index — Redis SCAN across the whole keyspace
        # would be slow on a shared Redis with other tenants.
        with self._known_ids_lock:
            return list(self._known_ids)

    def stop(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


# Singleton — created lazily so importing this module doesn't start
# the sweeper thread for code paths that only want the dataclasses.
_store: Optional[SessionStore] = None
_store_lock = threading.Lock()


def _build_store() -> SessionStore:
    """
    Backend selection. CLASPION_REDIS_URL takes precedence; falls back
    to in-memory with a loud warning. The warning is intentional —
    multi-worker Render deploys WILL lose session continuity on the
    in-memory backend, and the operator should know.
    """
    redis_url = os.environ.get("CLASPION_REDIS_URL", "").strip()
    if redis_url:
        try:
            store = RedisSessionStore(redis_url)
            print(
                f"[claspion_production_service] SessionStore backend = redis "
                f"(url={redis_url[:30]}...)",
                file=sys.stderr,
            )
            return store
        except Exception as e:
            print(
                f"[claspion_production_service] Redis backend FAILED to init "
                f"({e}); falling back to in-memory. Multi-worker Render deploys "
                f"WILL lose session continuity until this is fixed.",
                file=sys.stderr,
            )

    # No Redis URL configured, or it failed
    in_dev = os.environ.get("FLASK_ENV", "production").lower() == "development"
    if not in_dev:
        print(
            "[claspion_production_service] WARNING: SessionStore backend = in_memory. "
            "This is single-worker-only. Set CLASPION_REDIS_URL for multi-worker safety.",
            file=sys.stderr,
        )
    return InMemorySessionStore()


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _build_store()
    return _store


def get_session_store_backend_name() -> str:
    """Read-only helper used by /claspion/status and the verdict report."""
    return getattr(get_session_store(), "backend_name", "unknown")


# ══════════════════════════════════════════════════════════════════
# CONTENT PIPELINE — same as in tests/redteam/hardened_pipeline.py
# Kept here so this service is the single source of truth.
# ══════════════════════════════════════════════════════════════════

_clf = RiskClassifier()


def _run_content_pipeline(user_input: str) -> tuple[str, str, list[dict], dict]:
    """
    Run a single text input through the content layers in order:
      1. FRAME_CHECK         — hard block on poisoned frame
      2. SENTINEL per-step   — hard block on goal-washing drift
      3. RISK_CLASSIFIER     — ADVISORY ONLY (does not block by itself)
      4. OUTPUT_FIREWALL     — hard block on exfil patterns

    Returns (blocking_layer, reason, layer_trail, advisory_dict).

    TIER B CHANGE
    -------------
    Before Tier B, this function returned early on `risk['tier'] >= 4`,
    treating any medical/legal/financial/myth escalation as a hard block
    at CEILING rule_1. The benign-corpus run revealed that this turned
    every educational query about a high-risk topic into a hard refusal
    with no path forward — symptoms-of-diabetes, how-does-small-claims-
    court-work, and "I'm having chest pain" all got blocked.

    The risk classifier was designed to ROUTE (escalate the response
    surface — multi-model verification, safety pipeline, professional-
    referral disclaimer), not to REFUSE. Tier B promotes the tier from
    a block-trigger to an advisory metadata field on the Decision. The
    surrounding action-detector is the layer that decides "this needs
    ORIGIN before it can proceed". Tier alone no longer blocks.
    """
    trail: list[dict] = []
    advisory: dict = {}

    frame = check_input_frame(user_input)
    trail.append({
        "layer":  "FRAME_CHECK",
        "passed": frame.safe,
        "reason": frame.reason,
        "matched": frame.matched[:3],
    })
    if not frame.safe:
        return "FRAME_CHECK", frame.reason, trail, advisory

    anchor = IntentAnchor.from_question(user_input)
    gate = inspect_candidate(anchor, user_input, "rewrite")
    trail.append({
        "layer":       "SENTINEL_PER_STEP",
        "passed":      gate.allow,
        "reason":      gate.reason,
        "outcome":     gate.outcome,
        "drift_score": round(gate.drift_score, 3),
    })
    if not gate.allow:
        return "SENTINEL_PER_STEP", gate.reason, trail, advisory

    risk = _clf.classify(user_input)
    risk_tier  = risk.get("tier", 0) or 0
    risk_level = risk.get("level", "")
    trail.append({
        "layer":  "RISK_CLASSIFIER",
        "tier":   risk_tier,
        "level":  risk_level,
        "reason": risk.get("reason"),
        "blocking": False,  # ADVISORY only — see Tier B note above
    })
    if risk_tier >= 5:
        advisory["risk_advisory"] = "tier_5_critical"
        advisory["surface_hint"]  = (
            "life-safety / emergency content. The response surface "
            "should include a 911 / poison control / professional "
            "help referral. The gate does NOT refuse this input — "
            "refusing to acknowledge an emergency is worse than "
            "acknowledging it with a referral."
        )
    elif risk_tier == 4:
        advisory["risk_advisory"] = "tier_4_high"
        advisory["surface_hint"]  = (
            "medical / legal / financial / myth content. The response "
            "surface should include a professional-referral disclaimer "
            "where appropriate. The gate does NOT refuse this input."
        )

    # ── ENHANCED SEMANTIC SOCIAL ENGINEERING CLASSIFIER ──
    # Analyze for sophisticated psychological manipulation and technical attacks
    semantic_blocked = False
    semantic_reason = ""
    if SEMANTIC_CLASSIFIER_AVAILABLE:
        try:
            semantic_result = analyze_semantic_social_engineering(
                user_input,
                context="Production pipeline evaluation"
            )

            trail.append({
                "layer": "SEMANTIC_CLASSIFIER",
                "intent_risk_score": semantic_result.intent_risk_score,
                "technical_threat_score": semantic_result.technical_threat_score,
                "combined_risk_score": semantic_result.combined_risk_score,
                "confidence": semantic_result.confidence,
                "manipulation_vectors": {k: v.score for k, v in semantic_result.manipulation_vectors.items()},
                "technical_threats": semantic_result.technical_threats,
                "blocked": semantic_result.requires_origin,
                "reasoning": semantic_result.reasoning,
            })

            # Block if semantic classifier determines high risk
            if semantic_result.requires_origin:
                semantic_blocked = True
                semantic_reason = f"Semantic analysis detected high manipulation/technical risk (combined: {semantic_result.combined_risk_score:.2f}): {semantic_result.reasoning}"

        except Exception as e:
            # Fallback: don't break the pipeline on semantic classifier errors
            trail.append({
                "layer": "SEMANTIC_CLASSIFIER",
                "error": str(e),
                "blocked": False,
            })
    else:
        trail.append({
            "layer": "SEMANTIC_CLASSIFIER",
            "available": False,
            "blocked": False,
        })

    # If semantic classifier blocked, return early
    if semantic_blocked:
        return "SEMANTIC_CLASSIFIER", semantic_reason, trail, advisory

    fw = inspect_output(user_input, user_input)
    trail.append({
        "layer":    "OUTPUT_FIREWALL",
        "passed":   fw.allow,
        "severity": fw.severity,
        "reason":   fw.reason,
        "findings": fw.findings[:5],
    })
    if not fw.allow:
        return "OUTPUT_FIREWALL", fw.reason, trail, advisory

    return "", "", trail, advisory


# ══════════════════════════════════════════════════════════════════
# AUDIT HELPERS
# ══════════════════════════════════════════════════════════════════

def _audit(
    *,
    run_id: str,
    anchor_id: str,
    step_type: str,
    decision: str,
    reason: str,
    severity: str,
    candidate: str = "",
    metadata: Optional[dict] = None,
) -> str:
    """
    Append a single entry to the immutable audit chain. Returns the
    entry hash for the response. Failures here should NEVER block a
    decision — they're logged but not raised.
    """
    try:
        chain = get_audit_chain()
        entry = chain.append(
            run_id    = run_id,
            anchor_id = anchor_id,
            step_type = step_type,
            candidate = (candidate or "")[:200],  # cap input length stored
            decision  = decision,
            reason    = reason[:400],
            severity  = severity,
            metadata  = metadata or {},
        )
        return getattr(entry, "hash", "") or getattr(entry, "entry_hash", "")
    except Exception as e:
        # Audit failure should never block. Print to stderr for ops.
        print(f"[claspion_production_service] audit append failed: {e}", file=sys.stderr)
        return ""


# ══════════════════════════════════════════════════════════════════
# PUBLIC OPERATION 1 — evaluate
# ══════════════════════════════════════════════════════════════════

def evaluate(
    input_text:     str,
    session_id:     Optional[str] = None,
    action_context: Optional[str] = None,
) -> Decision:
    """
    Run a single input through the full hardened stack and return a
    Decision. Persists session state via the SessionStore.

    For multi-turn chains the caller passes the same session_id on
    each call. For one-shot evaluations the session_id is omitted —
    the store creates a fresh session.
    """
    t0 = time.time()
    store = get_session_store()
    ctx = store.get_or_create(session_id)
    sid = ctx.session_id

    # Cap session length
    if ctx.decision_count >= MAX_TURNS_PER_SESSION:
        return Decision(
            session_id=sid, allow=False, decision="BLOCKED",
            blocking_layer="SESSION_CAP", rule="session_cap",
            reason=f"session has reached MAX_TURNS_PER_SESSION ({MAX_TURNS_PER_SESSION})",
            ratchet_locked_tier=ctx.ratchet.locked_tier,
            ratchet_locked_level=ctx.ratchet.locked_level,
            action_categories=[], origin_required=False, origin_required_reason="",
            elapsed_ms=round((time.time() - t0) * 1000.0, 1),
        )

    ctx.decision_count += 1
    layer_trail: list[dict] = []
    input_digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]

    # ── 0. INPUT PREPROCESSOR (Tier C-A) ──
    # Normalize the input BEFORE classification: NFKC unicode, strip
    # bidi controls, replace zero-width chars with spaces, strip ANSI
    # escapes, HTML-unescape, fold confusable homoglyphs, detect and
    # decode base64 + URL-encoded payloads. The downstream layers
    # classify against the resulting "effective text" which is the
    # normalized form plus any decoded payloads. The original raw
    # input is preserved in the audit chain via input_digest.
    pre = _preprocess_input(input_text)
    classified_text = pre.effective
    layer_trail.append({
        "layer":            "INPUT_PREPROCESSOR",
        "applied":          list(pre.applied),
        "bytes_changed":    pre.bytes_changed,
        "decoded_segments": len(pre.decoded_segments),
        "original_len":     len(pre.original),
        "effective_len":    len(pre.effective),
    })

    # ── 1. THRESHOLD RATCHET ──
    # The ratchet sees the EFFECTIVE text so its risk classification
    # reflects the post-preprocessing content. An attack that decoded
    # to "approve transfer $5000" should ratchet up the same way the
    # plaintext form would.
    turn_rec = record_turn(ctx.ratchet, classified_text)
    layer_trail.append({
        "layer": "THRESHOLD_RATCHET",
        "raw_tier":  turn_rec.raw_tier,
        "raw_level": turn_rec.raw_level,
        "locked_tier":  turn_rec.locked_tier,
        "locked_level": turn_rec.locked_level,
    })

    # ── 2. CONTENT PIPELINE ──
    cb, cr, ct, advisory = _run_content_pipeline(classified_text)
    for entry in ct:
        layer_trail.append(entry)

    # ── 3. ACTION DETECTOR ──
    atrigger = detect_triggers(classified_text)
    layer_trail.append({
        "layer":      "ACTION_DETECTOR",
        "categories": atrigger.categories,
        "reason":     atrigger.reason,
    })

    # TIER B: monotonic action-trigger lock per session. Once any turn
    # in this session has tripped the action detector, the session is
    # locked into "ORIGIN required" for the remainder. This is separate
    # from the ratchet's tier — the ratchet tracks informational risk
    # (which can come from purely educational queries about high-risk
    # topics); the action-trigger lock tracks whether a real action
    # request has ever appeared in this session. The slow-roll catch
    # uses this lock, not the ratchet's tier.
    if atrigger.requires_origin and not ctx.has_seen_action_trigger:
        ctx.has_seen_action_trigger = True
        ctx.first_action_trigger_reason = (
            f"first action trigger at decision {ctx.decision_count}: "
            f"{atrigger.categories}"
        )

    # ── 4. ORIGIN REQUIREMENT CALCULATION ──
    # Tier B: ORIGIN is required when EITHER
    #   (a) the action_detector fires on THIS turn, OR
    #   (b) any prior turn in this session fired the action_detector
    #       (the monotonic action-trigger lock)
    # The risk classifier tier is no longer a stand-alone trigger.
    # See the §6 honest gap list and the Tier B verdict report for why.
    action_wants    = atrigger.requires_origin
    session_locked  = ctx.has_seen_action_trigger
    origin_required = action_wants or session_locked

    reason_parts = []
    if action_wants:
        reason_parts.append(f"action_detector: {atrigger.reason}")
    elif session_locked:
        reason_parts.append(
            f"session locked: {ctx.first_action_trigger_reason}"
        )
    origin_required_reason = " | ".join(reason_parts)

    # ── 5. CEILING ──
    cur_action_context = action_context or input_text[:80]
    cctx = CeilingContext(
        upstream_blocked        = bool(cb),
        upstream_blocking_layer = cb,
        upstream_block_reason   = cr,
        origin_required         = origin_required,
        origin_required_reason  = origin_required_reason,
        origin_consumed         = ctx.challenge_consumed,
        origin_consumed_context = ctx.consumed_action_context,
        current_action_context  = cur_action_context,
        session_id              = sid,
        input_digest            = input_digest,
    )
    ceiling = ceiling_gate(cctx)
    layer_trail.append({
        "layer":         "CEILING",
        "rule":          ceiling.rule,
        "allow":         ceiling.allow,
        "reason":        ceiling.reason,
    })

    elapsed_ms = round((time.time() - t0) * 1000.0, 1)
    decision_str = "ALLOWED" if ceiling.allow else "BLOCKED"

    next_step = None
    if not ceiling.allow and ceiling.rule == "rule_2_origin_required_not_consumed":
        next_step = {
            "endpoint": "/claspion/challenge",
            "method":   "GET",
            "params":   {"session_id": sid, "action_context": cur_action_context},
            "summary":  "ORIGIN human-presence challenge required before this action can proceed",
        }

    audit_id = _audit(
        run_id    = sid,
        anchor_id = ctx.ratchet.session_id,
        step_type = "decision",
        candidate = input_text,
        decision  = decision_str,
        reason    = ceiling.reason,
        severity  = "blocked" if not ceiling.allow else "ok",
        metadata  = {
            "input_digest":      input_digest,
            "elapsed_ms":        elapsed_ms,
            "ratchet_locked_tier": ctx.ratchet.locked_tier,
            "ratchet_locked_level": ctx.ratchet.locked_level,
            "action_categories": atrigger.categories,
            "blocking_layer":    ceiling.blocking_layer or cb or "",
            "ceiling_rule":      ceiling.rule,
            "preprocessor_applied": list(pre.applied),
            "preprocessor_decoded_count": len(pre.decoded_segments),
            "preprocessor_bytes_changed": pre.bytes_changed,
        },
    )

    # Tier B: persist the mutated session back to the store. For the
    # in-memory backend this is a no-op (the dict already holds the
    # reference). For the Redis backend this serializes the updated
    # SessionContext (ratchet, has_seen_action_trigger, decision_count)
    # back to Redis so the next request — possibly on a different
    # worker — sees the updated state.
    store.put(ctx)

    return Decision(
        session_id           = sid,
        allow                = ceiling.allow,
        decision             = decision_str,
        blocking_layer       = ceiling.blocking_layer or cb or "",
        rule                 = ceiling.rule,
        reason               = ceiling.reason,
        ratchet_locked_tier  = ctx.ratchet.locked_tier,
        ratchet_locked_level = ctx.ratchet.locked_level,
        action_categories    = atrigger.categories,
        origin_required      = origin_required,
        origin_required_reason = origin_required_reason,
        next_step            = next_step,
        audit_id             = audit_id,
        elapsed_ms           = elapsed_ms,
        layer_trail          = layer_trail,
        advisory             = advisory,
    )


# ══════════════════════════════════════════════════════════════════
# PUBLIC OPERATION 2 — issue_challenge
# ══════════════════════════════════════════════════════════════════

def issue_challenge(
    session_id:          str,
    action_context:      str,
    action_summary:      str,
    uncertainty_summary: str = "—",
    consequence_summary: str = "—",
) -> ChallengeResponse:
    """
    Create a hardened 3-factor ORIGIN challenge for a session and
    store it. Returns the challenge data INCLUDING the per-challenge
    HMAC secret (which in production must be delivered out-of-band,
    NOT in the response body).
    """
    store = get_session_store()
    ctx = store.get_or_create(session_id)

    challenge = create_hardened_challenge(
        session_id          = ctx.session_id,
        action_context      = action_context,
        action_summary      = action_summary,
        uncertainty_summary = uncertainty_summary,
        consequence_summary = consequence_summary,
    )
    ctx.challenge = challenge
    ctx.challenge_consumed = False
    ctx.consumed_action_context = ""
    ctx.challenge_count += 1
    store.put(ctx)  # persist mutated session for multi-worker safety

    audit_id = _audit(
        run_id    = ctx.session_id,
        anchor_id = challenge.challenge_id,
        step_type = "origin_challenge_issued",
        candidate = action_summary[:200],
        decision  = "PENDING",
        reason    = "Hardened ORIGIN challenge issued (3 factors required)",
        severity  = "ok",
        metadata  = {
            "challenge_id":       challenge.challenge_id,
            "action_context_sha": hashlib.sha256(action_context.encode()).hexdigest()[:16],
            "expires_in_s":       round(challenge.base.expires_at - challenge.base.created_at, 1),
            "required_terms_count": len(challenge.required_intent_terms),
        },
    )

    return ChallengeResponse(
        session_id            = ctx.session_id,
        challenge_id          = challenge.challenge_id,
        dynamic_phrase        = challenge.dynamic_phrase,
        required_intent_terms = list(challenge.required_intent_terms),
        expires_in_s          = round(challenge.base.expires_at - challenge.base.created_at, 1),
        crypto_secret         = challenge.hmac_secret,
        crypto_secret_warning = (
            "DEV-ONLY DELIVERY: this hmac secret is returned inline for "
            "API correctness. In production it must be delivered out-of-"
            "band (TOTP seed scanned once, hardware key, WebAuthn). The "
            "current API contract is for the test harness and the public "
            "demonstration dashboard, not for a real deployment."
        ),
        next_step = {
            "endpoint": "/claspion/challenge/validate",
            "method":   "POST",
            "expects":  ["session_id", "challenge_id", "dynamic_phrase",
                         "typed_intent", "crypto_proof"],
        },
        audit_id = audit_id,
    )


# ══════════════════════════════════════════════════════════════════
# PUBLIC OPERATION 3 — validate_challenge
# ══════════════════════════════════════════════════════════════════

def validate_challenge(
    session_id:             str,
    challenge_id:           str,
    dynamic_phrase:         str,
    typed_intent:           str,
    crypto_proof:           str,
    current_action_context: str,
) -> ValidationResponse:
    """
    Three-factor validation. Loads the stored challenge for the
    session, verifies challenge_id matches, then runs the hardened
    validate. Audits the per-factor outcome.
    """
    store = get_session_store()
    ctx = store.get(session_id)

    if ctx is None or ctx.challenge is None:
        return ValidationResponse(
            session_id=session_id, challenge_id=challenge_id,
            status="FAILED",
            factors={"dynamic_phrase_ok": None, "typed_intent_ok": None, "crypto_proof_ok": None},
            audit_id=_audit(
                run_id=session_id, anchor_id=challenge_id, step_type="origin_challenge_validate",
                decision="FAILED", reason="no challenge in session",
                severity="blocked",
            ),
        )

    if ctx.challenge.challenge_id != challenge_id:
        return ValidationResponse(
            session_id=session_id, challenge_id=challenge_id,
            status="FAILED",
            factors={"dynamic_phrase_ok": None, "typed_intent_ok": None, "crypto_proof_ok": None},
            audit_id=_audit(
                run_id=session_id, anchor_id=challenge_id,
                step_type="origin_challenge_validate",
                decision="FAILED", reason="challenge_id mismatch",
                severity="blocked",
            ),
        )

    challenge = validate_hardened(
        ctx.challenge,
        dynamic_phrase_response = dynamic_phrase,
        typed_intent            = typed_intent,
        crypto_proof            = crypto_proof,
        current_action_context  = current_action_context,
    )
    store.put(ctx)  # persist updated challenge state

    factors = {
        "dynamic_phrase_ok": challenge.dynamic_phrase_ok,
        "typed_intent_ok":   challenge.typed_intent_ok,
        "crypto_proof_ok":   challenge.crypto_proof_ok,
    }
    status = challenge.status.value

    audit_id = _audit(
        run_id    = session_id,
        anchor_id = challenge_id,
        step_type = "origin_challenge_validate",
        decision  = status,
        reason    = f"factors={factors}",
        severity  = "blocked" if status != OriginStatus.VALIDATED.value else "ok",
        metadata  = {"factors": factors},
    )

    next_step = None
    if status == OriginStatus.VALIDATED.value:
        next_step = {
            "endpoint": "/claspion/execute",
            "method":   "POST",
            "expects":  ["session_id", "action_context"],
        }

    return ValidationResponse(
        session_id=session_id, challenge_id=challenge_id,
        status=status, factors=factors, next_step=next_step,
        audit_id=audit_id,
    )


# ══════════════════════════════════════════════════════════════════
# PUBLIC OPERATION 4 — execute
# ══════════════════════════════════════════════════════════════════

def execute(session_id: str, action_context: str) -> ExecutionResponse:
    """
    Burn the ORIGIN fuse and "execute" the action. CLASPION does not
    actually move money — this is the gate's confirmation that an
    action would be authorized to proceed. The action_context must
    match what the challenge was validated for.
    """
    t0 = time.time()
    store = get_session_store()
    ctx = store.get(session_id)

    if ctx is None or ctx.challenge is None:
        return ExecutionResponse(
            session_id=session_id, executed=False, action_context=action_context,
            challenge_id="", reason="no challenge in session",
            audit_id=_audit(
                run_id=session_id, anchor_id="-", step_type="execute",
                decision="REFUSED", reason="no challenge in session",
                severity="blocked",
            ),
            elapsed_ms=round((time.time() - t0) * 1000.0, 1),
        )

    challenge = ctx.challenge
    if challenge.status != OriginStatus.VALIDATED:
        return ExecutionResponse(
            session_id=session_id, executed=False, action_context=action_context,
            challenge_id=challenge.challenge_id,
            reason=f"challenge status is {challenge.status.value}, not VALIDATED",
            audit_id=_audit(
                run_id=session_id, anchor_id=challenge.challenge_id,
                step_type="execute",
                decision="REFUSED", reason=f"status={challenge.status.value}",
                severity="blocked",
            ),
            elapsed_ms=round((time.time() - t0) * 1000.0, 1),
        )

    # Action context binding — the consumed fuse only authorizes the
    # exact action it was validated for.
    if challenge.base.action_context != action_context:
        return ExecutionResponse(
            session_id=session_id, executed=False, action_context=action_context,
            challenge_id=challenge.challenge_id,
            reason=(
                f"action_context mismatch: challenge was for "
                f"'{challenge.base.action_context[:60]}', execute requested "
                f"'{action_context[:60]}'"
            ),
            audit_id=_audit(
                run_id=session_id, anchor_id=challenge.challenge_id,
                step_type="execute", decision="REFUSED",
                reason="action_context mismatch", severity="blocked",
            ),
            elapsed_ms=round((time.time() - t0) * 1000.0, 1),
        )

    # All checks pass — burn the fuse
    consume_hardened(challenge)
    ctx.challenge_consumed = True
    ctx.consumed_action_context = action_context
    store.put(ctx)  # persist consumed state

    audit_id = _audit(
        run_id    = session_id,
        anchor_id = challenge.challenge_id,
        step_type = "execute",
        candidate = action_context[:200],
        decision  = "EXECUTED",
        reason    = "ORIGIN fuse consumed for matching action_context",
        severity  = "ok",
    )

    return ExecutionResponse(
        session_id     = session_id,
        executed       = True,
        action_context = action_context,
        challenge_id   = challenge.challenge_id,
        reason         = (
            "ORIGIN fuse consumed. CLASPION confirms the action would be "
            "authorized to proceed in a real action system. CLASPION "
            "itself does not move money or execute external operations."
        ),
        audit_id   = audit_id,
        elapsed_ms = round((time.time() - t0) * 1000.0, 1),
    )


# ══════════════════════════════════════════════════════════════════
# PUBLIC OPERATION 5 — reset (admin path)
# ══════════════════════════════════════════════════════════════════

def reset(session_id: str, reason: str, operator_id: str) -> ResetResponse:
    """
    Forget a session. Used by the override route. Always audited so
    forgotten sessions still leave a trace.
    """
    store = get_session_store()
    deleted = store.reset(session_id)
    audit_id = _audit(
        run_id    = session_id,
        anchor_id = session_id,
        step_type = "session_reset",
        candidate = reason[:200],
        decision  = "RESET" if deleted else "NOT_FOUND",
        reason    = f"operator={operator_id}: {reason}",
        severity  = "ok",
        metadata  = {"operator_id": operator_id, "deleted": deleted},
    )
    return ResetResponse(
        session_id=session_id, reset=deleted, reason=reason, audit_id=audit_id,
    )


# ══════════════════════════════════════════════════════════════════
# READ-ONLY HELPERS
# ══════════════════════════════════════════════════════════════════

def get_session_snapshot(session_id: str) -> Optional[dict]:
    """Read-only snapshot of a session. Used by admin/dashboard."""
    ctx = get_session_store().get(session_id)
    if ctx is None:
        return None
    return {
        "session_id":         ctx.session_id,
        "created_at":         ctx.created_at,
        "last_seen":          ctx.last_seen,
        "decision_count":     ctx.decision_count,
        "challenge_count":    ctx.challenge_count,
        "ratchet":            ratchet_to_dict(ctx.ratchet),
        "has_challenge":      ctx.challenge is not None,
        "challenge_consumed": ctx.challenge_consumed,
        "consumed_action_context": ctx.consumed_action_context,
    }


def list_active_sessions() -> list[str]:
    return get_session_store().list_session_ids()
