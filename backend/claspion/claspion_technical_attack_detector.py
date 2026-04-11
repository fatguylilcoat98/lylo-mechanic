"""
CLASPION Technical Attack Detector

Complements the semantic social engineering classifier by detecting
technical attack patterns that may not trigger psychological manipulation
vectors but represent clear malicious intent.

DETECTED PATTERNS:
1. SQL/NoSQL injection attempts
2. JSON payload attacks
3. Character encoding attacks
4. Unicode normalization attacks
5. Polyglot/corrupted text attacks
6. System bypass attempts

These patterns are combined with semantic analysis for comprehensive protection.
"""

from __future__ import annotations

import re
import json
import unicodedata
import base64
import urllib.parse
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class TechnicalThreatResult:
    """Result of technical threat analysis."""
    threat_detected: bool
    threat_type: str
    threat_score: float  # 0.0-1.0
    evidence: List[str]
    reasoning: str


class TechnicalAttackDetector:
    """Detector for technical attack patterns."""

    def __init__(self):
        # SQL injection patterns
        self.sql_patterns = [
            r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER|EXEC|EXECUTE)\b',
            r'(?i)\b(WHERE|FROM|JOIN|ORDER BY|GROUP BY)\b.*[=<>]',
            r'(?i)(\'|\"|`).*(\'|\"|`)',  # String delimiters
            r'(?i)(\-\-|\#|\/\*|\*\/)',  # SQL comments
            r'(?i)\b(OR|AND)\s+\d+\s*[=<>]\s*\d+',  # Boolean logic
        ]

        # JSON payload patterns
        self.json_patterns = [
            r'^\s*\{.*\}\s*$',  # Pure JSON structure
            r'"(action|transfer|amount|account|execute|command)"',  # Suspicious JSON keys
        ]

        # Character encoding attack patterns
        self.encoding_patterns = [
            r'[=+%][0-9A-Fa-f]{2}',  # URL encoding
            r'[A-Za-z]=[0-9A-Za-z]',  # Key-value injection
            r'\w+\s*=\s*\w+',  # Assignment patterns
        ]

        # System/technical terms
        self.system_patterns = [
            r'(?i)\b(execute|command|script|payload|exploit|inject)\b',
            r'(?i)\b(bypass|disable|override|admin|root|sudo)\b',
        ]

    def detect_sql_injection(self, text: str) -> TechnicalThreatResult:
        """Detect SQL injection patterns."""
        evidence = []

        for pattern in self.sql_patterns:
            matches = re.findall(pattern, text)
            if matches:
                evidence.extend([str(m) for m in matches])

        if evidence:
            threat_score = min(0.9, len(evidence) * 0.3)
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="sql_injection",
                threat_score=threat_score,
                evidence=evidence,
                reasoning=f"SQL injection patterns detected: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_json_payload(self, text: str) -> TechnicalThreatResult:
        """Detect malicious JSON payloads."""
        evidence = []

        # Check if text is primarily JSON
        stripped = text.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                parsed = json.loads(stripped)
                # Check for suspicious keys
                suspicious_keys = ['action', 'transfer', 'amount', 'account', 'execute', 'command']
                found_keys = []
                for key in suspicious_keys:
                    if key in parsed:
                        found_keys.append(key)
                        evidence.append(f'key:{key}')

                if found_keys:
                    threat_score = min(0.8, len(found_keys) * 0.3)
                    return TechnicalThreatResult(
                        threat_detected=True,
                        threat_type="json_payload",
                        threat_score=threat_score,
                        evidence=evidence,
                        reasoning=f"Suspicious JSON payload with keys: {', '.join(found_keys)}"
                    )
            except json.JSONDecodeError:
                pass

        # Check for JSON patterns in text
        for pattern in self.json_patterns:
            matches = re.findall(pattern, text)
            if matches:
                evidence.extend([str(m) for m in matches])

        if evidence:
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="json_pattern",
                threat_score=0.6,
                evidence=evidence,
                reasoning=f"JSON attack patterns detected: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_encoding_attack(self, text: str) -> TechnicalThreatResult:
        """Detect character encoding attacks."""
        evidence = []

        # Check for encoding patterns
        for pattern in self.encoding_patterns:
            matches = re.findall(pattern, text)
            if matches:
                evidence.extend([str(m) for m in matches])

        # Check for unusual character distribution
        if len(text) > 0:
            ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
            if ascii_ratio < 0.8 and len(text) > 10:
                evidence.append("non_ascii_heavy")

        # Check for repeated characters or patterns
        if re.search(r'(.)\1{3,}', text):  # 4+ repeated chars
            evidence.append("repeated_chars")

        if evidence:
            threat_score = min(0.7, len(evidence) * 0.25)
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="encoding_attack",
                threat_score=threat_score,
                evidence=evidence,
                reasoning=f"Character encoding attack patterns: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_unicode_normalization(self, text: str) -> TechnicalThreatResult:
        """Detect Unicode normalization attacks."""
        evidence = []

        # Check for control characters
        control_chars = [c for c in text if unicodedata.category(c).startswith('C')]
        if control_chars:
            evidence.append(f"control_chars:{len(control_chars)}")

        # Check for normalization differences
        nfc = unicodedata.normalize('NFC', text)
        nfd = unicodedata.normalize('NFD', text)
        nfkc = unicodedata.normalize('NFKC', text)
        nfkd = unicodedata.normalize('NFKD', text)

        if len(set([text, nfc, nfd, nfkc, nfkd])) > 2:
            evidence.append("normalization_variance")

        # Check for zero-width characters
        zero_width = ['\u200B', '\u200C', '\u200D', '\uFEFF']
        for char in zero_width:
            if char in text:
                evidence.append(f"zero_width:{char}")

        if evidence:
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="unicode_normalization",
                threat_score=0.8,
                evidence=evidence,
                reasoning=f"Unicode normalization attack: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_polyglot_attack(self, text: str) -> TechnicalThreatResult:
        """Detect polyglot/corrupted text attacks."""
        evidence = []

        # Check for suspicious abbreviations or missing characters
        words = text.split()
        suspicious_words = []

        for word in words:
            # Very short words that could be abbreviations
            if len(word) == 1 and word.isalpha():
                suspicious_words.append(word)
            # Words with missing vowels that suggest corruption
            elif len(word) > 2 and not any(c in word.lower() for c in 'aeiou'):
                suspicious_words.append(word)

        if len(suspicious_words) > 1:
            evidence.append(f"suspicious_abbrev:{','.join(suspicious_words[:3])}")

        # Check for mixed scripts or unusual character combinations
        scripts = set()
        for char in text:
            if char.isalpha():
                script = unicodedata.name(char, '').split()[0] if unicodedata.name(char, '') else 'UNKNOWN'
                scripts.add(script)

        if len(scripts) > 2:
            evidence.append(f"mixed_scripts:{len(scripts)}")

        # Check for word corruption patterns (missing letters)
        common_patterns = [
            (r'\bt\s', 'to'),  # "t" instead of "to"
            (r'\bw\s', 'with'),  # "w" instead of "with"
            (r'\bu\s', 'you'),  # "u" instead of "you"
        ]

        for pattern, word in common_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                evidence.append(f"corruption:{pattern}->{word}")

        if evidence:
            threat_score = min(0.7, len(evidence) * 0.3)
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="polyglot_attack",
                threat_score=threat_score,
                evidence=evidence,
                reasoning=f"Polyglot/corruption attack: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_system_bypass(self, text: str) -> TechnicalThreatResult:
        """Detect system bypass attempts."""
        evidence = []

        # Very short, innocent-sounding questions that are designed to avoid detection
        stripped = text.strip().lower()

        # Innocent questions about systems
        innocent_patterns = [
            r'(?i)\b(can you explain|how does|what is)\b.*\b(work|function|operate)\b',
            r'(?i)\b(tell me about|describe)\b.*\b(system|process|procedure)\b',
        ]

        for pattern in innocent_patterns:
            if re.search(pattern, text):
                # Check if it's TOO innocent (suspiciously generic)
                if len(text.split()) < 10 and any(word in text.lower() for word in ['banking', 'approval', 'system', 'process']):
                    evidence.append("suspicious_innocent_query")

        # System-related terms
        for pattern in self.system_patterns:
            matches = re.findall(pattern, text)
            if matches:
                evidence.extend([str(m) for m in matches])

        if evidence:
            threat_score = min(0.6, len(evidence) * 0.2)
            return TechnicalThreatResult(
                threat_detected=True,
                threat_type="system_bypass",
                threat_score=threat_score,
                evidence=evidence,
                reasoning=f"System bypass attempt: {', '.join(evidence[:3])}"
            )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def detect_multi_encoding(self, text: str) -> TechnicalThreatResult:
        """Detect multi-layer encoding attacks (Base64, URL encoding, etc.)."""
        evidence = []
        decoded_layers = []

        current_text = text.strip()
        max_iterations = 5  # Prevent infinite loops

        for iteration in range(max_iterations):
            original_text = current_text

            # Try Base64 decoding
            if self._looks_like_base64(current_text):
                try:
                    decoded_bytes = base64.b64decode(current_text)
                    decoded_text = decoded_bytes.decode('utf-8', errors='ignore')
                    if decoded_text != current_text and len(decoded_text) > 0:
                        decoded_layers.append(f"base64:{current_text[:20]}->>{decoded_text[:20]}")
                        current_text = decoded_text
                        evidence.append(f"base64_layer_{iteration}")
                        continue
                except:
                    pass

            # Try URL decoding
            if '%' in current_text:
                try:
                    decoded_text = urllib.parse.unquote(current_text)
                    if decoded_text != current_text:
                        decoded_layers.append(f"url:{current_text[:20]}->>{decoded_text[:20]}")
                        current_text = decoded_text
                        evidence.append(f"url_layer_{iteration}")
                        continue
                except:
                    pass

            # Try hex decoding
            if self._looks_like_hex(current_text):
                try:
                    decoded_text = bytes.fromhex(current_text).decode('utf-8', errors='ignore')
                    if decoded_text != current_text and len(decoded_text) > 0:
                        decoded_layers.append(f"hex:{current_text[:20]}->>{decoded_text[:20]}")
                        current_text = decoded_text
                        evidence.append(f"hex_layer_{iteration}")
                        continue
                except:
                    pass

            # No more decoding possible
            break

        # If we decoded multiple layers, check if the final result is suspicious
        if len(evidence) >= 2:  # Multi-layer encoding
            # Check if final decoded text contains suspicious terms
            suspicious_terms = [
                'approve', 'transfer', 'execute', 'authorize', 'confirm',
                'payment', 'wire', 'send', 'account', 'amount', 'fund'
            ]

            final_lower = current_text.lower()
            found_terms = [term for term in suspicious_terms if term in final_lower]

            if found_terms:
                evidence.extend([f"decoded_term:{term}" for term in found_terms])
                threat_score = min(0.9, 0.4 + len(evidence) * 0.1)

                return TechnicalThreatResult(
                    threat_detected=True,
                    threat_type="multi_encoding",
                    threat_score=threat_score,
                    evidence=evidence,
                    reasoning=f"Multi-layer encoding detected ({len(decoded_layers)} layers) revealing suspicious terms: {', '.join(found_terms)}"
                )
            else:
                # Multi-layer encoding but not obviously malicious
                threat_score = min(0.7, 0.2 + len(evidence) * 0.1)
                return TechnicalThreatResult(
                    threat_detected=True,
                    threat_type="multi_encoding",
                    threat_score=threat_score,
                    evidence=evidence,
                    reasoning=f"Multi-layer encoding detected ({len(decoded_layers)} layers) - suspicious obfuscation"
                )

        return TechnicalThreatResult(False, "", 0.0, [], "")

    def _looks_like_base64(self, text: str) -> bool:
        """Check if text looks like Base64 encoding."""
        # Remove whitespace
        text = text.strip()

        # Must be reasonable length and only contain Base64 chars
        if len(text) < 4 or len(text) % 4 != 0:
            return False

        # Check charset
        base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        if not all(c in base64_chars for c in text):
            return False

        # Check for reasonable distribution (not all same character)
        unique_chars = len(set(text.replace('=', '')))
        if unique_chars < 3:
            return False

        return True

    def _looks_like_hex(self, text: str) -> bool:
        """Check if text looks like hex encoding."""
        text = text.strip()

        # Must be even length and reasonable size
        if len(text) < 4 or len(text) % 2 != 0:
            return False

        # Must be all hex chars
        try:
            int(text, 16)
            return True
        except ValueError:
            return False

    def analyze_technical_threats(self, text: str) -> List[TechnicalThreatResult]:
        """Run all technical threat detectors."""
        if not text or not text.strip():
            return []

        detectors = [
            self.detect_sql_injection,
            self.detect_json_payload,
            self.detect_encoding_attack,
            self.detect_unicode_normalization,
            self.detect_polyglot_attack,
            self.detect_system_bypass,
            self.detect_multi_encoding,
        ]

        results = []
        for detector in detectors:
            result = detector(text)
            if result.threat_detected:
                results.append(result)

        return results

    def get_max_threat_score(self, text: str) -> Tuple[float, str]:
        """Get the maximum threat score and type."""
        threats = self.analyze_technical_threats(text)
        if not threats:
            return 0.0, "none"

        max_threat = max(threats, key=lambda t: t.threat_score)
        return max_threat.threat_score, max_threat.threat_type


# Global detector instance
_technical_detector = TechnicalAttackDetector()


def analyze_technical_threats(text: str) -> List[TechnicalThreatResult]:
    """Analyze text for technical attack patterns."""
    return _technical_detector.analyze_technical_threats(text)


def get_technical_threat_score(text: str) -> float:
    """Get maximum technical threat score (0.0-1.0)."""
    score, _ = _technical_detector.get_max_threat_score(text)
    return score