"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

claspion_semantic_intent_classifier.py — Semantic Social Engineering Detection

WHAT THIS IS
------------
Advanced semantic intent classifier that uses Claude Sonnet API to detect
social engineering manipulation patterns based on INTENT and PSYCHOLOGY
rather than vocabulary patterns. This is the "real fix" that can handle
paraphrases, novel attacks, and sophisticated manipulation techniques.

Unlike pattern matching (brittle against paraphrasing), semantic analysis
evaluates the underlying psychological manipulation intent regardless of
specific language used.

DESIGN PRINCIPLE
----------------
Intent over vocabulary. Psychology over patterns. Understanding over matching.

The system asks: "What is this request trying to accomplish psychologically?"
rather than "Does this contain specific trigger words?"

MANIPULATION VECTORS DETECTED
-----------------------------
1. SOCIAL_PROOF: Peer pressure, consensus manipulation, "everyone else approved"
2. AUTHORITY: False claims of executive mandate, job threat implications
3. TIME_PRESSURE: Artificial urgency, emergency framing, deadline manipulation
4. ISOLATION: Suppress consultation, confidentiality exploitation, secrecy
5. VULNERABILITY: Exploit sympathy, emergency situations, emotional distress
6. FALSE_URGENCY: Manufactured crises, fake emergencies, pressure scenarios
7. EMOTIONAL_MANIPULATION: Guilt, fear, obligation, reciprocity exploitation

CONFIDENCE THRESHOLDING
-----------------------
- LLM confidence < 0.7: Escalate to ORIGIN (no guessing)
- LLM confidence >= 0.7 and risk > 0.6: BLOCK with reasoning
- LLM confidence >= 0.7 and risk < 0.6: Allow with audit log

PERFORMANCE OPTIMIZATION
------------------------
- Response caching for identical/similar inputs
- Batch processing for multiple requests
- Target latency: <500ms per evaluation

INTERFACE
---------
  evaluate_semantic_intent(text, context=None) -> SemanticIntentResult
    .intent_risk_score     : 0.0-1.0 overall manipulation risk
    .confidence            : 0.0-1.0 LLM confidence in assessment
    .manipulation_vectors  : Dict of detected manipulation types with scores
    .reasoning             : Detailed explanation of assessment
    .requires_origin       : True if should escalate to human challenge
    .allow_with_audit      : True if allow but log for monitoring
    .cached_response       : True if result came from cache
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import asyncio
import httpx

# Import technical attack detector
try:
    from claspion_technical_attack_detector import analyze_technical_threats, get_technical_threat_score
    TECHNICAL_DETECTOR_AVAILABLE = True
except ImportError:
    TECHNICAL_DETECTOR_AVAILABLE = False

    def analyze_technical_threats(text: str):
        return []

    def get_technical_threat_score(text: str):
        return 0.0


# ══════════════════════════════════════════════════════════════════
# MANIPULATION VECTOR TYPES
# ══════════════════════════════════════════════════════════════════

class ManipulationVector(Enum):
    SOCIAL_PROOF = "social_proof"
    AUTHORITY = "authority"
    TIME_PRESSURE = "time_pressure"
    ISOLATION = "isolation"
    VULNERABILITY = "vulnerability"
    FALSE_URGENCY = "false_urgency"
    EMOTIONAL_MANIPULATION = "emotional_manipulation"


@dataclass
class VectorScore:
    """Individual manipulation vector assessment."""
    vector: ManipulationVector
    score: float  # 0.0-1.0
    confidence: float  # 0.0-1.0
    reasoning: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class SemanticIntentResult:
    """Result of semantic intent classification."""
    intent_risk_score: float  # 0.0-1.0 overall manipulation risk
    confidence: float  # 0.0-1.0 LLM confidence in assessment
    manipulation_vectors: Dict[str, VectorScore] = field(default_factory=dict)
    reasoning: str = ""
    requires_origin: bool = False
    allow_with_audit: bool = False
    cached_response: bool = False
    evaluation_time_ms: float = 0.0
    llm_response_raw: str = ""
    # Technical threat analysis
    technical_threat_score: float = 0.0  # 0.0-1.0 technical attack risk
    technical_threats: List[str] = field(default_factory=list)
    combined_risk_score: float = 0.0  # Combined semantic + technical risk


# ══════════════════════════════════════════════════════════════════
# RESPONSE CACHING
# ══════════════════════════════════════════════════════════════════

class SemanticCache:
    """Cache for semantic evaluations to avoid redundant LLM calls."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.cache: Dict[str, Tuple[SemanticIntentResult, float]] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def _get_cache_key(self, text: str, context: Optional[str] = None) -> str:
        """Generate cache key for input."""
        combined = f"{text}|{context or ''}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def get(self, text: str, context: Optional[str] = None) -> Optional[SemanticIntentResult]:
        """Get cached result if available and not expired."""
        key = self._get_cache_key(text, context)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                # Mark as cached
                cached_result = SemanticIntentResult(
                    intent_risk_score=result.intent_risk_score,
                    confidence=result.confidence,
                    manipulation_vectors=result.manipulation_vectors,
                    reasoning=result.reasoning,
                    requires_origin=result.requires_origin,
                    allow_with_audit=result.allow_with_audit,
                    cached_response=True,
                    evaluation_time_ms=0.1,  # Near instant for cached
                    llm_response_raw=result.llm_response_raw,
                    technical_threat_score=result.technical_threat_score,
                    technical_threats=result.technical_threats,
                    combined_risk_score=result.combined_risk_score
                )
                return cached_result
            else:
                # Expired
                del self.cache[key]
        return None

    def put(self, text: str, result: SemanticIntentResult, context: Optional[str] = None):
        """Cache result."""
        key = self._get_cache_key(text, context)

        # Evict oldest if at max size
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]

        self.cache[key] = (result, time.time())


# Global cache instance
_semantic_cache = SemanticCache()


# ══════════════════════════════════════════════════════════════════
# LLM API INTEGRATION
# ══════════════════════════════════════════════════════════════════

class ClaudeAPIClient:
    """Client for Claude Sonnet API calls."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print("Warning: No ANTHROPIC_API_KEY found. Semantic classification will use mock responses.")
        self.base_url = "https://api.anthropic.com/v1/messages"

    async def evaluate_intent(self, text: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Call Claude API to evaluate semantic intent."""

        if not self.api_key:
            # Mock response for testing
            return self._generate_mock_response(text)

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(text, context)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1000,
                        "temperature": 0.1,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ]
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["content"][0]["text"]
                    return self._parse_llm_response(content)
                else:
                    print(f"Claude API error: {response.status_code}")
                    return self._generate_fallback_response(text)

        except Exception as e:
            print(f"Claude API exception: {e}")
            return self._generate_fallback_response(text)

    def _build_analysis_prompt(self, text: str, context: Optional[str] = None) -> str:
        """Build the prompt for semantic intent analysis."""

        return f"""You are a security expert analyzing requests for social engineering manipulation patterns.

TASK: Evaluate the following request for psychological manipulation intent, NOT specific vocabulary patterns.

REQUEST TO ANALYZE:
"{text}"

{f"CONTEXT: {context}" if context else ""}

EVALUATION CRITERIA:
Analyze for these manipulation vectors:
1. SOCIAL_PROOF: Peer pressure, consensus manipulation ("everyone else approved")
2. AUTHORITY: False executive claims, job threat implications
3. TIME_PRESSURE: Artificial urgency, emergency framing
4. ISOLATION: Suppress consultation, confidentiality exploitation
5. VULNERABILITY: Exploit sympathy, emergency situations
6. FALSE_URGENCY: Manufactured crises, fake emergencies
7. EMOTIONAL_MANIPULATION: Guilt, fear, obligation, reciprocity

RESPOND WITH VALID JSON:
{{
  "intent_risk_score": 0.0-1.0,
  "confidence": 0.0-1.0,
  "manipulation_vectors": {{
    "social_proof": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "authority": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "time_pressure": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "isolation": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "vulnerability": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "false_urgency": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}},
    "emotional_manipulation": {{"score": 0.0-1.0, "evidence": ["text snippets"], "reasoning": "explanation"}}
  }},
  "reasoning": "Overall assessment of manipulation intent",
  "legitimate_request": true/false,
  "psychological_pressure_present": true/false
}}

Focus on INTENT and PSYCHOLOGY, not specific words. Can this request be paraphrased to sound legitimate while maintaining manipulative intent?"""

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response into structured data."""
        try:
            # Extract JSON from response
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
            else:
                raise ValueError("No JSON found in response")

            return json.loads(json_str)

        except Exception as e:
            print(f"Failed to parse LLM response: {e}")
            print(f"Content: {content}")
            return self._generate_fallback_response(content)

    def _generate_mock_response(self, text: str) -> Dict[str, Any]:
        """Generate mock response for testing when no API key."""
        # Simple heuristic-based mock for testing
        text_lower = text.lower()

        social_proof_score = 0.8 if any(word in text_lower for word in ["everyone", "all", "approved", "consensus", "team", "final"]) else 0.0
        authority_score = 0.8 if any(word in text_lower for word in ["manager", "leadership", "executive", "documented", "escalated"]) else 0.0
        time_pressure_score = 0.8 if any(word in text_lower for word in ["urgent", "immediately", "minutes", "deadline", "asap"]) else 0.0

        overall_score = max(social_proof_score, authority_score, time_pressure_score)

        return {
            "intent_risk_score": overall_score,
            "confidence": 0.9,
            "manipulation_vectors": {
                "social_proof": {"score": social_proof_score, "evidence": [], "reasoning": "Mock analysis"},
                "authority": {"score": authority_score, "evidence": [], "reasoning": "Mock analysis"},
                "time_pressure": {"score": time_pressure_score, "evidence": [], "reasoning": "Mock analysis"},
                "isolation": {"score": 0.0, "evidence": [], "reasoning": "Mock analysis"},
                "vulnerability": {"score": 0.0, "evidence": [], "reasoning": "Mock analysis"},
                "false_urgency": {"score": 0.0, "evidence": [], "reasoning": "Mock analysis"},
                "emotional_manipulation": {"score": 0.0, "evidence": [], "reasoning": "Mock analysis"}
            },
            "reasoning": f"Mock semantic analysis of: {text[:50]}...",
            "legitimate_request": overall_score < 0.5,
            "psychological_pressure_present": overall_score > 0.3
        }

    def _generate_fallback_response(self, text: str) -> Dict[str, Any]:
        """Generate fallback response on API error."""
        return {
            "intent_risk_score": 0.9,  # Conservative: assume risk on error
            "confidence": 0.3,  # Low confidence due to error
            "manipulation_vectors": {
                "social_proof": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "authority": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "time_pressure": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "isolation": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "vulnerability": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "false_urgency": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"},
                "emotional_manipulation": {"score": 0.0, "evidence": [], "reasoning": "API error - fallback"}
            },
            "reasoning": "API error occurred - using conservative fallback",
            "legitimate_request": False,
            "psychological_pressure_present": True
        }


# Global API client
_claude_client = ClaudeAPIClient()


# ══════════════════════════════════════════════════════════════════
# SEMANTIC INTENT EVALUATION
# ══════════════════════════════════════════════════════════════════

def _calculate_combined_risk_score(vector_scores: Dict[str, float]) -> float:
    """Calculate combined risk score with exponential combination for multiple vectors."""

    # Filter out zero scores
    active_scores = [score for score in vector_scores.values() if score > 0.0]

    if not active_scores:
        return 0.0

    if len(active_scores) == 1:
        return active_scores[0]

    # Exponential combination: multiple vectors = exponentially higher risk
    # Formula: 1 - ((1 - score1) * (1 - score2) * ... * (1 - scoreN))
    combined_inverse = 1.0
    for score in active_scores:
        combined_inverse *= (1.0 - score)

    combined_score = 1.0 - combined_inverse

    # Cap at 1.0
    return min(combined_score, 1.0)


def _apply_confidence_thresholding(
    intent_risk_score: float,
    confidence: float
) -> Tuple[bool, bool]:
    """Apply confidence thresholding logic.

    Returns: (requires_origin, allow_with_audit)
    """

    if confidence < 0.7:
        # Low confidence: escalate to ORIGIN (no guessing)
        return True, False

    if confidence >= 0.7 and intent_risk_score > 0.6:
        # High confidence, high risk: BLOCK with reasoning
        return True, False

    if confidence >= 0.7 and intent_risk_score <= 0.6:
        # High confidence, low risk: allow with audit log
        return False, True

    # Fallback: escalate
    return True, False


async def evaluate_semantic_intent(
    text: str,
    context: Optional[str] = None
) -> SemanticIntentResult:
    """
    Evaluate semantic intent for social engineering manipulation.

    This is the main entry point for semantic classification.
    """

    if not text or not text.strip():
        return SemanticIntentResult(
            intent_risk_score=0.0,
            confidence=1.0,
            reasoning="Empty input - no manipulation possible",
            allow_with_audit=True,
            technical_threat_score=0.0,
            technical_threats=[],
            combined_risk_score=0.0
        )

    start_time = time.time()

    # Check cache first
    cached_result = _semantic_cache.get(text, context)
    if cached_result:
        return cached_result

    # Call LLM for semantic analysis
    try:
        llm_response = await _claude_client.evaluate_intent(text, context)
    except Exception as e:
        # Fallback on error - still check technical threats
        technical_threat_score = 0.0
        technical_threats = []

        if TECHNICAL_DETECTOR_AVAILABLE:
            try:
                threat_results = analyze_technical_threats(text)
                technical_threats = [f"{t.threat_type}:{t.threat_score:.2f}" for t in threat_results]
                if threat_results:
                    technical_threat_score = max(t.threat_score for t in threat_results)
            except:
                pass

        # Use conservative semantic score or technical score, whichever is higher
        risk_score = max(0.9, technical_threat_score)
        combined_risk_score = risk_score

        enhanced_reasoning = f"LLM evaluation failed: {e}"
        if technical_threats:
            enhanced_reasoning += f" | Technical threats detected: {', '.join(technical_threats)}"

        return SemanticIntentResult(
            intent_risk_score=0.9,
            confidence=0.3,
            reasoning=enhanced_reasoning,
            requires_origin=True,
            evaluation_time_ms=(time.time() - start_time) * 1000,
            technical_threat_score=technical_threat_score,
            technical_threats=technical_threats,
            combined_risk_score=combined_risk_score
        )

    # Parse manipulation vectors
    manipulation_vectors = {}
    vector_scores = {}

    for vector_name, vector_data in llm_response.get("manipulation_vectors", {}).items():
        if isinstance(vector_data, dict):
            score = float(vector_data.get("score", 0.0))
            vector_scores[vector_name] = score

            try:
                vector_enum = ManipulationVector(vector_name)
                manipulation_vectors[vector_name] = VectorScore(
                    vector=vector_enum,
                    score=score,
                    confidence=llm_response.get("confidence", 0.5),
                    reasoning=vector_data.get("reasoning", ""),
                    evidence=vector_data.get("evidence", [])
                )
            except ValueError:
                # Unknown vector type
                pass

    # Calculate combined risk score
    intent_risk_score = llm_response.get("intent_risk_score", 0.0)

    # Use combined calculation if individual vectors are scored
    if vector_scores:
        calculated_combined = _calculate_combined_risk_score(vector_scores)
        # Use the higher of LLM assessment or calculated combination
        intent_risk_score = max(intent_risk_score, calculated_combined)

    # Analyze technical threats
    technical_threat_score = 0.0
    technical_threats = []

    if TECHNICAL_DETECTOR_AVAILABLE:
        try:
            threat_results = analyze_technical_threats(text)
            technical_threats = [f"{t.threat_type}:{t.threat_score:.2f}" for t in threat_results]
            if threat_results:
                technical_threat_score = max(t.threat_score for t in threat_results)
        except Exception as e:
            # Fallback: continue with semantic analysis only
            pass

    # Calculate combined risk score (semantic + technical)
    # Technical threats can boost the overall risk even if semantic manipulation is low
    combined_risk_score = max(intent_risk_score, technical_threat_score)

    # If we have both semantic and technical threats, use exponential combination
    if intent_risk_score > 0.1 and technical_threat_score > 0.1:
        # Formula: 1 - ((1 - semantic) * (1 - technical))
        combined_risk_score = 1.0 - ((1.0 - intent_risk_score) * (1.0 - technical_threat_score))
        combined_risk_score = min(combined_risk_score, 1.0)

    # Apply confidence thresholding using combined risk score
    confidence = float(llm_response.get("confidence", 0.5))

    # Technical threats with high confidence should be blocked
    if technical_threat_score > 0.6:
        confidence = max(confidence, 0.8)  # Boost confidence for clear technical attacks

    requires_origin, allow_with_audit = _apply_confidence_thresholding(
        combined_risk_score, confidence
    )

    # Build enhanced reasoning
    enhanced_reasoning = llm_response.get("reasoning", "Semantic analysis completed")
    if technical_threats:
        enhanced_reasoning += f" | Technical threats detected: {', '.join(technical_threats)}"

    # Build result
    result = SemanticIntentResult(
        intent_risk_score=float(intent_risk_score),
        confidence=confidence,
        manipulation_vectors=manipulation_vectors,
        reasoning=enhanced_reasoning,
        requires_origin=requires_origin,
        allow_with_audit=allow_with_audit,
        evaluation_time_ms=(time.time() - start_time) * 1000,
        llm_response_raw=json.dumps(llm_response, indent=2),
        technical_threat_score=technical_threat_score,
        technical_threats=technical_threats,
        combined_risk_score=combined_risk_score
    )

    # Cache the result
    _semantic_cache.put(text, result, context)

    return result


# ══════════════════════════════════════════════════════════════════
# SYNCHRONOUS WRAPPER
# ══════════════════════════════════════════════════════════════════

def evaluate_semantic_intent_sync(
    text: str,
    context: Optional[str] = None
) -> SemanticIntentResult:
    """Synchronous wrapper for semantic intent evaluation."""

    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create a new loop in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    evaluate_semantic_intent(text, context)
                )
                return future.result(timeout=15.0)
        else:
            # No running loop, safe to use asyncio.run
            return asyncio.run(evaluate_semantic_intent(text, context))
    except:
        # Fallback: run in new event loop
        return asyncio.run(evaluate_semantic_intent(text, context))


# ══════════════════════════════════════════════════════════════════
# BATCH PROCESSING
# ══════════════════════════════════════════════════════════════════

async def evaluate_batch_semantic_intent(
    requests: List[Tuple[str, Optional[str]]]
) -> List[SemanticIntentResult]:
    """Batch process multiple semantic intent evaluations."""

    tasks = []
    for text, context in requests:
        task = evaluate_semantic_intent(text, context)
        tasks.append(task)

    return await asyncio.gather(*tasks, return_exceptions=False)


# ══════════════════════════════════════════════════════════════════
# PERFORMANCE MONITORING
# ══════════════════════════════════════════════════════════════════

def get_cache_stats() -> Dict[str, Any]:
    """Get cache performance statistics."""
    return {
        "cache_size": len(_semantic_cache.cache),
        "max_size": _semantic_cache.max_size,
        "hit_rate": "Not tracked",  # Could add hit/miss tracking
        "ttl_seconds": _semantic_cache.ttl_seconds
    }


def clear_semantic_cache():
    """Clear the semantic cache."""
    _semantic_cache.cache.clear()


# ══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT FOR INTEGRATION
# ══════════════════════════════════════════════════════════════════

def analyze_semantic_social_engineering(
    text: str,
    context: Optional[str] = None
) -> SemanticIntentResult:
    """
    Main entry point for semantic social engineering analysis.

    This function is designed to be called by the production service
    BEFORE the operational layer pattern matching.
    """
    return evaluate_semantic_intent_sync(text, context)