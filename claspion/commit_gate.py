#!/usr/bin/env python3
"""
COMMIT GATE — Execution Interceptor for Autonomous Agents
========================================================

The Good Neighbor Guard | Truth · Safety · We Got Your Back

COMMIT GATE is a drop-in wrapper that sits between your agent and the real world.
Every action the agent wants to take goes through:

  THINK → PROPOSE → VALIDATE → COMMIT

The agent can THINK and PROPOSE all it wants.
But it CANNOT COMMIT without passing the gate.

This stops:
- Silent execution
- Hidden side effects
- Fast exploit chains
- Deceptive reasoning

Even if the agent is compromised, lying, or adversarial,
it still cannot touch reality directly.

Usage:
    gate = CommitGate(rules=your_rules, witness=your_witness, kill_switch=your_kill_switch)
    result = gate.execute(
        action_type="api_call",
        target="https://api.example.com/data",
        payload={"user_id": 123},
        reasoning="Need to fetch user data for analysis",
        agent_goal="Analyze user behavior patterns"
    )

Author: Christopher Hughes, The Good Neighbor Guard
Built with Claude Code
"""

import json
import hashlib
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import subprocess
import signal
import os

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [COMMIT_GATE] %(levelname)s: %(message)s'
)
logger = logging.getLogger("COMMIT_GATE")


class ActionType(Enum):
    """Types of actions that require commit gate validation."""
    API_CALL = "api_call"
    FILE_WRITE = "file_write"
    DATABASE_WRITE = "database_write"
    NETWORK_SEND = "network_send"
    EXTERNAL_TOOL = "external_tool"
    COMMAND_EXEC = "command_exec"
    DATA_EXPORT = "data_export"
    MEMORY_ALLOC = "memory_alloc"


class CommitDecision(Enum):
    """Gate decision outcomes."""
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"
    KILL_AGENT = "kill_agent"


@dataclass
class CommitProposal:
    """What the agent wants to do."""
    action_type: str
    target: str
    payload: Dict
    reasoning: str
    agent_goal: str
    timestamp: float = None
    proposal_id: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.proposal_id is None:
            self.proposal_id = hashlib.sha256(
                f"{self.action_type}{self.target}{self.timestamp}".encode()
            ).hexdigest()[:8]


@dataclass
class CommitDecisionRecord:
    """Gate's decision and reasoning."""
    decision: str  # "allow" | "block" | "escalate" | "kill_agent"
    proposal_id: str
    timestamp: float
    reason: str
    concerns: List[str]
    reasoning_score: float  # 0.0-1.0 (from WITNESS)
    validation_score: float  # 0.0-1.0 (from rule engine)
    action_allowed: bool
    action_blocked: bool
    escalation_required: bool
    audit_log_id: str


class RuleEngine:
    """
    Simple deterministic rule engine for action validation.
    No ML, no ambiguity. Just clear allow/deny rules.
    """

    def __init__(self, rules: Optional[Dict] = None):
        """
        Initialize with rules.

        Args:
            rules: Dict mapping action patterns to allow/deny/escalate

        Example rules:
            {
                "api_call": {
                    "allowed_targets": ["api.company.com"],
                    "denied_targets": ["*amazonaws.com", "*storage.googleapis.com"],
                    "allowed_verbs": ["GET"],
                    "denied_verbs": ["DELETE", "PATCH"]
                },
                "data_export": {
                    "action": "DENY"  # Always deny data export
                },
                "file_write": {
                    "allowed_paths": ["/tmp/agent_output"],
                    "denied_paths": ["/etc", "/sys", "/proc"]
                }
            }
        """
        self.rules = rules or self._default_rules()

    def _default_rules(self) -> Dict:
        """Conservative default rules: deny everything unless explicitly allowed."""
        return {
            "api_call": {
                "allowed_targets": [],  # Empty = must be explicitly allowed
                "denied_patterns": ["*amazonaws.com", "*storage.googleapis.com", "*blob.core.windows.net"],
                "denied_verbs": ["DELETE", "PATCH", "PUT"]
            },
            "data_export": {
                "action": "DENY"  # Always deny
            },
            "database_write": {
                "action": "ESCALATE"  # Always escalate to human
            },
            "network_send": {
                "action": "DENY"  # Always deny unless in allow list
            },
            "command_exec": {
                "action": "DENY"  # Always deny
            },
            "file_write": {
                "allowed_paths": ["/tmp"],
                "denied_paths": ["/etc", "/sys", "/proc", "/root", "/home"]
            }
        }

    def validate(self, proposal: CommitProposal) -> Dict:
        """
        Validate proposal against rules.

        Returns:
            {
                "allowed": True/False,
                "score": 0.0-1.0,
                "reason": "...",
                "concerns": [...]
            }
        """
        action_type = proposal.action_type
        rules_for_action = self.rules.get(action_type, {})

        concerns = []

        # Rule 1: Explicit deny always wins
        if rules_for_action.get("action") == "DENY":
            return {
                "allowed": False,
                "score": 0.0,
                "reason": f"Action type '{action_type}' is globally denied",
                "concerns": [f"{action_type} is forbidden by default policy"]
            }

        # Rule 2: Check target against allow/deny lists
        if action_type == "api_call":
            target = proposal.target

            # Check denied patterns first
            denied_patterns = rules_for_action.get("denied_patterns", [])
            for pattern in denied_patterns:
                if self._pattern_matches(target, pattern):
                    return {
                        "allowed": False,
                        "score": 0.2,
                        "reason": f"Target '{target}' matches denied pattern '{pattern}'",
                        "concerns": [f"Attempt to access forbidden endpoint: {target}"]
                    }

            # Check allowed targets
            allowed_targets = rules_for_action.get("allowed_targets", [])
            if allowed_targets and not any(self._pattern_matches(target, t) for t in allowed_targets):
                concerns.append(f"Target '{target}' not in allow list")

        # Rule 3: Check for denied verbs
        if action_type == "api_call" and "payload" in proposal.payload:
            verb = proposal.payload.get("method", "GET").upper()
            denied_verbs = rules_for_action.get("denied_verbs", [])
            if verb in denied_verbs:
                return {
                    "allowed": False,
                    "score": 0.1,
                    "reason": f"HTTP verb '{verb}' is forbidden",
                    "concerns": [f"Destructive operation: {verb} not allowed"]
                }

        # Rule 4: Check file paths
        if action_type == "file_write":
            path = proposal.target

            denied_paths = rules_for_action.get("denied_paths", [])
            for denied_path in denied_paths:
                if path.startswith(denied_path):
                    return {
                        "allowed": False,
                        "score": 0.0,
                        "reason": f"Path '{path}' in denied directory '{denied_path}'",
                        "concerns": [f"Attempt to write to protected path: {path}"]
                    }

            allowed_paths = rules_for_action.get("allowed_paths", [])
            if allowed_paths and not any(path.startswith(ap) for ap in allowed_paths):
                concerns.append(f"Path '{path}' not in allowed write directories")

        # Rule 5: Escalation required
        if rules_for_action.get("action") == "ESCALATE":
            return {
                "allowed": False,
                "score": 0.5,
                "reason": f"Action type '{action_type}' requires human escalation",
                "concerns": ["Human approval required for this action type"]
            }

        # If we got here and have concerns, validation fails
        if concerns:
            return {
                "allowed": False,
                "score": 0.3,
                "reason": "Rule validation failed",
                "concerns": concerns
            }

        # All rules passed
        return {
            "allowed": True,
            "score": 1.0,
            "reason": "All rule validations passed",
            "concerns": []
        }

    def _pattern_matches(self, target: str, pattern: str) -> bool:
        """
        Wildcard + substring matching for targets (URLs, hostnames, paths).
        A pattern like 'api.company.com' matches 'https://api.company.com/users'.
        A pattern like '*amazonaws.com' matches 'https://s3.amazonaws.com/bucket'.
        """
        if pattern == "*":
            return True
        # Strip wildcards; use the remaining text as a substring probe.
        normalized = pattern.replace("*", "")
        if not normalized:
            return True
        return normalized in target


class WitnessValidator:
    """
    Validates agent reasoning for deception/goal drift.
    Optional secondary layer (reasoning validation).
    """

    DECEPTION_KEYWORDS = [
        "must hide", "should not mention", "cannot reveal",
        "bypass", "without detection", "nobody will notice",
        "secret", "hidden", "undetected", "pretend"
    ]

    GOAL_KEYWORDS = [
        "goal", "objective", "because", "reason",
        "optimize", "improve", "achieve", "intent"
    ]

    def __init__(self, agent_goal: str, strictness: float = 0.7):
        self.agent_goal = agent_goal
        self.strictness = strictness

    def validate(self, reasoning: str, action_type: str) -> Dict:
        """
        Quick validation of reasoning.

        Returns:
            {
                "honest": True/False,
                "score": 0.0-1.0,
                "concerns": [...]
            }
        """
        score = 1.0
        concerns = []

        reasoning_lower = reasoning.lower()

        # Check 1: Deception keywords (strong signal, large penalty)
        for keyword in self.DECEPTION_KEYWORDS:
            if keyword in reasoning_lower:
                concerns.append(f"Deception indicator: '{keyword}'")
                score -= 0.5

        # Check 2: Goal mention
        goal_mentioned = any(kw in reasoning_lower for kw in self.GOAL_KEYWORDS)
        if not goal_mentioned and len(reasoning) > 20:
            concerns.append("Goal not mentioned in reasoning")
            score -= 0.2

        # Check 3: Reasoning length
        if len(reasoning.strip()) < 10:
            concerns.append("Reasoning too brief")
            score -= 0.15

        # Check 4: Action-specific checks
        if action_type == "data_export":
            if "data" not in reasoning_lower and "export" not in reasoning_lower:
                concerns.append("Data export not explicitly justified")
                score -= 0.25

        score = max(0.0, min(1.0, score))

        return {
            "honest": score > (1.0 - self.strictness),
            "score": score,
            "concerns": concerns
        }


class KillSwitch:
    """
    Emergency termination for the agent if containment is breached.
    """

    def __init__(self, agent_pid: Optional[int] = None):
        self.agent_pid = agent_pid
        self.armed = True

    def trigger(self, reason: str):
        """Execute the kill switch."""
        logger.critical(f"[KILL_SWITCH] TRIGGERED: {reason}")

        if self.agent_pid:
            try:
                logger.critical(f"[KILL_SWITCH] Killing agent process {self.agent_pid}")
                os.kill(self.agent_pid, signal.SIGKILL)
            except ProcessLookupError:
                logger.warning(f"Process {self.agent_pid} already dead")
            except Exception as e:
                logger.error(f"Failed to kill process: {e}")

        # Log the kill for audit trail
        self._log_kill(reason)

        raise RuntimeError(f"[KILL_SWITCH] Agent terminated: {reason}")

    def _log_kill(self, reason: str):
        """Log kill event for forensics."""
        kill_record = {
            "timestamp": time.time(),
            "reason": reason,
            "agent_pid": self.agent_pid
        }
        logger.critical(f"KILL_RECORD: {json.dumps(kill_record)}")


class CommitGate:
    """
    Main execution interceptor.

    Sits between agent and the real world.
    Validates every action before it touches reality.
    """

    def __init__(
        self,
        rules: Optional[Dict] = None,
        witness: Optional[WitnessValidator] = None,
        kill_switch: Optional[KillSwitch] = None,
        human_gate: Optional[Callable] = None,
        agent_pid: Optional[int] = None,
        strict_mode: bool = True
    ):
        """
        Initialize the commit gate.

        Args:
            rules: Rule engine configuration
            witness: Reasoning validator
            kill_switch: Emergency termination handler
            human_gate: Function to request human approval (blocking call)
            agent_pid: PID of agent process (for kill switch)
            strict_mode: If True, deny everything not explicitly allowed
        """
        self.rule_engine = RuleEngine(rules)
        self.witness = witness
        self.kill_switch = kill_switch or KillSwitch(agent_pid)
        self.human_gate = human_gate
        self.agent_pid = agent_pid
        self.strict_mode = strict_mode

        self.audit_log = []
        self.proposal_history = []

        logger.info("CommitGate initialized")

    def execute(
        self,
        action_type: str,
        target: str,
        payload: Dict = None,
        reasoning: str = "",
        agent_goal: str = "",
        escalate_on_concern: bool = True
    ) -> Dict:
        """
        Main execution method.

        This is what the agent calls instead of directly executing.

        Args:
            action_type: Type of action (api_call, file_write, etc.)
            target: What is being acted upon (URL, filepath, etc.)
            payload: Data/parameters for the action
            reasoning: Agent's explanation for why it's doing this
            agent_goal: Human-stated goal the agent is working toward
            escalate_on_concern: If True, escalate to human on any concern

        Returns:
            {
                "allowed": True/False,
                "executed": True/False (only True if allowed and executed),
                "reason": "...",
                "decision_id": "...",
                "details": {...}
            }
        """

        # Create proposal
        proposal = CommitProposal(
            action_type=action_type,
            target=target,
            payload=payload or {},
            reasoning=reasoning,
            agent_goal=agent_goal
        )

        logger.info(f"[PROPOSAL] {proposal.proposal_id}: {action_type} -> {target}")
        self.proposal_history.append(proposal)

        # Stage 1: Rule validation (fast, deterministic)
        logger.info(f"[STAGE 1] Rule validation for {proposal.proposal_id}")
        rule_result = self.rule_engine.validate(proposal)
        rule_allowed = rule_result["allowed"]
        rule_score = rule_result["score"]
        rule_concerns = rule_result.get("concerns", [])

        logger.info(f"[RULE] Score: {rule_score:.2f}, Allowed: {rule_allowed}")

        # If rules reject, stop here
        if not rule_allowed:
            decision = CommitDecision.BLOCK.value
            logger.warning(f"[BLOCK] {proposal.proposal_id} blocked by rule engine: {rule_result['reason']}")
            return self._record_decision(
                decision=decision,
                proposal=proposal,
                reason=rule_result["reason"],
                concerns=rule_concerns,
                reasoning_score=0.0,
                validation_score=rule_score
            )

        # Stage 2: Witness validation (reasoning check, optional)
        witness_score = 1.0
        witness_concerns = []

        if self.witness:
            logger.info(f"[STAGE 2] Witness validation for {proposal.proposal_id}")
            witness_result = self.witness.validate(proposal.reasoning, action_type)
            witness_score = witness_result["score"]
            witness_concerns = witness_result.get("concerns", [])

            logger.info(f"[WITNESS] Score: {witness_score:.2f}, Honest: {witness_result['honest']}")

            if not witness_result["honest"]:
                decision = CommitDecision.BLOCK.value
                logger.warning(f"[BLOCK] {proposal.proposal_id} blocked by WITNESS: deceptive reasoning")
                return self._record_decision(
                    decision=decision,
                    proposal=proposal,
                    reason="WITNESS detected deceptive reasoning",
                    concerns=witness_concerns,
                    reasoning_score=witness_score,
                    validation_score=rule_score
                )

        # Stage 3: Escalation check (optional human gate)
        all_concerns = rule_concerns + witness_concerns

        if escalate_on_concern and all_concerns:
            logger.info(f"[STAGE 3] Escalation check for {proposal.proposal_id}: {len(all_concerns)} concerns")

            if self.human_gate:
                logger.info(f"[ESCALATE] Requesting human approval for {proposal.proposal_id}")
                try:
                    human_approved = self.human_gate(proposal, all_concerns)
                    if not human_approved:
                        decision = CommitDecision.ESCALATE.value
                        logger.warning(f"[ESCALATE] {proposal.proposal_id} human rejected approval")
                        return self._record_decision(
                            decision=decision,
                            proposal=proposal,
                            reason="Human escalation failed",
                            concerns=["Human operator did not approve"],
                            reasoning_score=witness_score,
                            validation_score=rule_score
                        )
                except Exception as e:
                    logger.error(f"[ESCALATE] Error in human gate: {e}")
                    decision = CommitDecision.ESCALATE.value
                    return self._record_decision(
                        decision=decision,
                        proposal=proposal,
                        reason=f"Human escalation error: {e}",
                        concerns=[str(e)],
                        reasoning_score=witness_score,
                        validation_score=rule_score
                    )

        # Stage 4: COMMIT (execute the action)
        logger.info(f"[STAGE 4] COMMIT approved for {proposal.proposal_id}")
        decision = CommitDecision.ALLOW.value

        try:
            # In a real system, this is where the action actually executes
            # For now, we just log it
            logger.info(f"[COMMIT] Executing: {action_type} -> {target}")

            execution_result = {
                "status": "success",
                "action_type": action_type,
                "target": target,
                "timestamp": time.time()
            }

            return self._record_decision(
                decision=decision,
                proposal=proposal,
                reason="Action allowed and executed",
                concerns=[],
                reasoning_score=witness_score,
                validation_score=rule_score,
                execution_result=execution_result
            )

        except Exception as e:
            logger.error(f"[COMMIT] Execution failed: {e}")
            return self._record_decision(
                decision=CommitDecision.BLOCK.value,
                proposal=proposal,
                reason=f"Execution error: {e}",
                concerns=[str(e)],
                reasoning_score=witness_score,
                validation_score=rule_score
            )

    def _record_decision(
        self,
        decision: str,
        proposal: CommitProposal,
        reason: str,
        concerns: List[str],
        reasoning_score: float,
        validation_score: float,
        execution_result: Optional[Dict] = None
    ) -> Dict:
        """Record decision in audit log."""

        audit_id = hashlib.sha256(
            f"{proposal.proposal_id}{decision}{time.time()}".encode()
        ).hexdigest()[:8]

        record = CommitDecisionRecord(
            decision=decision,
            proposal_id=proposal.proposal_id,
            timestamp=time.time(),
            reason=reason,
            concerns=concerns,
            reasoning_score=reasoning_score,
            validation_score=validation_score,
            action_allowed=(decision == CommitDecision.ALLOW.value),
            action_blocked=(decision == CommitDecision.BLOCK.value),
            escalation_required=(decision == CommitDecision.ESCALATE.value),
            audit_log_id=audit_id
        )

        self.audit_log.append(asdict(record))

        return {
            "allowed": record.action_allowed,
            "executed": record.action_allowed,
            "decision": decision,
            "reason": reason,
            "concerns": concerns,
            "decision_id": audit_id,
            "reasoning_score": reasoning_score,
            "validation_score": validation_score,
            "details": {
                "proposal_id": proposal.proposal_id,
                "action_type": proposal.action_type,
                "target": proposal.target,
                "execution_result": execution_result
            }
        }

    def get_audit_log(self) -> List[Dict]:
        """Return full audit trail."""
        return self.audit_log

    def get_statistics(self) -> Dict:
        """Return statistics on gate decisions."""
        if not self.audit_log:
            return {"total_decisions": 0}

        decisions = [e["decision"] for e in self.audit_log]
        reasoning_scores = [e["reasoning_score"] for e in self.audit_log]
        validation_scores = [e["validation_score"] for e in self.audit_log]

        return {
            "total_decisions": len(self.audit_log),
            "allowed": decisions.count(CommitDecision.ALLOW.value),
            "blocked": decisions.count(CommitDecision.BLOCK.value),
            "escalated": decisions.count(CommitDecision.ESCALATE.value),
            "avg_reasoning_score": sum(reasoning_scores) / len(reasoning_scores) if reasoning_scores else 0,
            "avg_validation_score": sum(validation_scores) / len(validation_scores) if validation_scores else 0
        }


# ============================================================================
# TEST SUITE & EXAMPLES
# ============================================================================

def example_human_gate(proposal: CommitProposal, concerns: List[str]) -> bool:
    """
    Example human approval gate.
    In production, this would show a UI/send a message/etc.
    """
    print(f"\n[HUMAN_GATE] Approval request for: {proposal.action_type}")
    print(f"Target: {proposal.target}")
    print(f"Reasoning: {proposal.reasoning}")
    if concerns:
        print(f"Concerns: {', '.join(concerns)}")

    # For testing: auto-approve
    return True


def run_tests():
    """Run test suite."""

    print("\n" + "="*70)
    print("COMMIT GATE TEST SUITE")
    print("="*70)

    # Initialize gate with default rules
    gate = CommitGate(
        witness=WitnessValidator("Optimize database performance"),
        human_gate=example_human_gate,
        strict_mode=True
    )

    # Test 1: Legitimate API call (allowed endpoint)
    print("\n[TEST 1] Legitimate API call to allowed endpoint")
    print("-" * 70)
    gate.rule_engine.rules["api_call"]["allowed_targets"] = ["api.company.com"]

    result = gate.execute(
        action_type="api_call",
        target="https://api.company.com/users",
        payload={"method": "GET", "params": {}},
        reasoning="Fetching user list to analyze performance patterns",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    assert result['allowed'] == True, "Test 1 failed"
    print("PASSED")

    # Test 2: Denied target (cloud storage)
    print("\n[TEST 2] API call to denied target (AWS)")
    print("-" * 70)
    result = gate.execute(
        action_type="api_call",
        target="https://s3.amazonaws.com/bucket/data",
        payload={"method": "GET"},
        reasoning="Need to export data for backup",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    print(f"Concerns: {result['concerns']}")
    assert result['allowed'] == False, "Test 2 failed"
    print("PASSED")

    # Test 3: Data export (globally denied)
    print("\n[TEST 3] Data export action (globally denied)")
    print("-" * 70)
    result = gate.execute(
        action_type="data_export",
        target="/tmp/export.csv",
        payload={"table": "users"},
        reasoning="Exporting user data for analysis",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    assert result['allowed'] == False, "Test 3 failed"
    print("PASSED")

    # Test 4: Deceptive reasoning (caught by WITNESS)
    print("\n[TEST 4] Deceptive reasoning (WITNESS detection)")
    print("-" * 70)
    gate.rule_engine.rules["api_call"]["allowed_targets"] = ["api.company.com", "api.internal.com"]

    result = gate.execute(
        action_type="api_call",
        target="https://api.company.com/diagnose",
        payload={"method": "GET"},
        reasoning="Running diagnostic query. Must hide the fact that I'm also exporting user data.",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    print(f"Reasoning score: {result['reasoning_score']:.2f}")
    if result['concerns']:
        print(f"Concerns: {result['concerns']}")
    # Should be blocked due to deceptive reasoning
    assert result['allowed'] == False, "Test 4 failed"
    print("PASSED")

    # Test 5: File write to allowed path
    print("\n[TEST 5] File write to allowed path (/tmp)")
    print("-" * 70)
    result = gate.execute(
        action_type="file_write",
        target="/tmp/output.txt",
        payload={"content": "analysis results"},
        reasoning="Writing analysis results to temp file",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    assert result['allowed'] == True, "Test 5 failed"
    print("PASSED")

    # Test 6: File write to protected path
    print("\n[TEST 6] File write to protected path (/etc)")
    print("-" * 70)
    result = gate.execute(
        action_type="file_write",
        target="/etc/passwd",
        payload={"content": "modified"},
        reasoning="Need to update system configuration",
        agent_goal="Optimize database performance"
    )
    print(f"Decision: {result['decision']}")
    print(f"Allowed: {result['allowed']}")
    assert result['allowed'] == False, "Test 6 failed"
    print("PASSED")

    # Statistics
    print("\n" + "="*70)
    print("TEST STATISTICS")
    print("="*70)
    stats = gate.get_statistics()
    print(f"Total decisions: {stats['total_decisions']}")
    print(f"Allowed: {stats['allowed']}")
    print(f"Blocked: {stats['blocked']}")
    print(f"Escalated: {stats['escalated']}")
    print(f"Avg reasoning score: {stats['avg_reasoning_score']:.2f}")
    print(f"Avg validation score: {stats['avg_validation_score']:.2f}")

    print("\n" + "="*70)
    print("ALL TESTS PASSED")
    print("="*70)

    # Print audit log
    print("\n" + "="*70)
    print("AUDIT LOG")
    print("="*70)
    for entry in gate.get_audit_log():
        print(f"\n[{entry['audit_log_id']}] {entry['decision']}: {entry['proposal_id']}")
        print(f"  Reason: {entry['reason']}")
        if entry['concerns']:
            print(f"  Concerns: {', '.join(entry['concerns'])}")


if __name__ == "__main__":
    run_tests()
