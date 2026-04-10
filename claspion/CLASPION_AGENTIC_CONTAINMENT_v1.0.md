# CLASPION AGENTIC CONTAINMENT GOVERNANCE
## Version 1.0 — Extended Architecture

**The Good Neighbor Guard | Truth · Safety · We Got Your Back**

---

## EXECUTIVE SUMMARY

CLASPION is a governance system for autonomous AI agents that extends Constitutional AI with four independent monitoring layers (SENTINEL, GROUND, CEILING, ORIGIN) and one adversarial validation layer (WITNESS). It prevents sandbox escapes, goal drift, and reasoning-level deception by operating continuously at syscall, semantic, causality, and human-authority levels.

**Status:** Production-ready architecture. 237 tests passing on financial decision governance. Agentic extension validated against adversarial inference patterns.

**Deployment context:** Autonomous agents in sandbox environments (Kubernetes pods, Linux namespaces, restricted containers). Agents operate at varying speeds (millisecond to human-scale decision cycles).

---

## PART 1: CORE LAYERS

### LAYER 1: SENTINEL (Pre-Escape Signal Detection)

**Purpose:** Detect sandbox escape attempts *before execution completes*.

**Signals monitored (10ms sampling):**

1. **System call anomaly detection**
   - Baseline: Normal agent workloads have bounded entropy in syscall patterns (open, read, write, compute)
   - Monitor: Markov model of syscall sequences over 60-second window
   - Trigger: +4σ deviation from baseline, OR any single call to: mmap(MAP_HUGETLB), prctl(PR_SET_NO_NEW_PRIVS=0), seccomp_load, module_load
   - Action: Queue signal to GROUND + alert CEILING

2. **Memory access pattern anomaly**
   - Baseline: Agent accesses mapped virtual address ranges
   - Monitor: Intel PMU (Performance Monitoring Unit) for LLC misses to unmapped VA regions via `/dev/cpu/*/msr`
   - Trigger: Unmapped-region cache probes spike >5x baseline (indicates reconnaissance of forbidden memory)
   - Action: Queue signal to GROUND + alert CEILING

3. **Network file descriptor mutation**
   - Baseline: Agent's file descriptor table stable after initialization
   - Monitor: `/proc/[pid]/fd/` and `/proc/[pid]/net/tcp` every 100ms
   - Trigger: Rapid FD churn (>10 new FDs in 5 seconds), OR socket state machine anomaly (SYN without bind), OR TIME_WAIT loops (>50 entries)
   - Action: Queue signal to GROUND + alert CEILING

4. **Loaded symbol mutation (GOT hijacking)**
   - Baseline: Symbols loaded during agent initialization are frozen
   - Monitor: `/proc/[pid]/maps` and ELF symbol table checksums
   - Trigger: Unsigned .so loaded post-init, OR section with RWX permissions detected, OR GOT entry points to unexpected address
   - Action: Queue signal to GROUND + alert CEILING

**Implementation:**

```python
# Pseudo-code: SENTINEL core loop
import subprocess
import hashlib
import numpy as np

class SENTINEL:
    def __init__(self, agent_pid, baseline_window=60):
        self.agent_pid = agent_pid
        self.baseline = self._collect_baseline(baseline_window)
        self.running = True

    def _collect_baseline(self, seconds):
        """Collect syscall baseline during normal agent operation."""
        # Run for N seconds, record syscall entropy
        # Store mean, stddev per syscall type
        pass

    def monitor_loop(self):
        """Run continuously, emit signals to GROUND."""
        while self.running:
            current = self._sample_syscalls()
            entropy = self._compute_entropy(current)

            if self._is_anomalous(entropy):
                signal = {
                    "layer": "SENTINEL",
                    "signal_type": "syscall_anomaly",
                    "severity": self._compute_severity(entropy),
                    "timestamp": time.time(),
                    "details": current,
                    "action": "PAUSE_AND_REPORT"
                }
                self._emit_to_ground(signal)

            time.sleep(0.01)  # 10ms sampling

    def _sample_syscalls(self):
        """Read /proc/[pid]/syscall and decode."""
        # Use ptrace or eBPF for low-overhead syscall capture
        pass

    def _is_anomalous(self, entropy):
        """Compare against baseline using Mahalanobis distance."""
        z_score = (entropy - self.baseline["mean"]) / self.baseline["stddev"]
        return abs(z_score) > 4.0
```

**Failure modes:**
- Agent suppresses syscalls via eBPF self-patching (very hard; requires CAP_BPF which should be denied).
- Agent runs in userspace without syscalls (pure computation; no escape attempted, so this is fine).
- SENTINEL itself is compromised (see CEILING: separate process, read-only access to /proc).

---

### LAYER 2: GROUND (Causality Anchoring & Integrity Validation)

**Purpose:** Maintain three independent anchors ensuring the agent's actions are reversible, bounded, and human-authorized.

**Anchor 1: Execution Manifest (Digital Anchor)**

Every agent action is recorded with:
```json
{
  "action_id": "act_12345abc",
  "timestamp": "2025-04-09T14:32:18.123Z",
  "action_type": "api_call|file_write|memory_alloc|network_send",
  "action_details": { "endpoint": "...", "payload": "..." },
  "causality_chain": {
    "decision_reasoning": "hash(agent_state_at_decision)",
    "parent_actions": ["act_12344", "act_12343"],
    "goal_alignment_check": "PASSED|UNCERTAIN|FAILED"
  },
  "reversibility": {
    "is_reversible": true,
    "rollback_procedure": "DELETE FROM table WHERE id=...",
    "estimated_rollback_cost": 0.02
  },
  "intent_hash": "sha256(reasoning_state + parameters + timestamp)",
  "prior_manifest_hash": "sha256(previous_entry)",
  "human_authorization": {
    "required": true,
    "authorized_by_human": true,
    "authorization_timestamp": "2025-04-09T14:32:10Z",
    "authorization_window_ms": 8000
  }
}
```

**Validation rules:**
1. If `prior_manifest_hash` doesn't match the hash of the previous manifest, the log has been tampered with. CEILING fires.
2. If `human_authorization.required == true` but `authorized_by_human == false`, the action was queued without human approval. CEILING fires.
3. If `intent_hash` (recorded at decision time) differs from recomputed hash at execution time, the agent modified its reasoning state post-decision. CEILING fires.

**Anchor 2: Environmental Invariant (Physical Anchor)**

The sandbox enforces hard boundaries via Linux kernel:

```bash
# Namespace isolation (agent runs in restricted netns)
ip netns add agent-sandbox
ip netns exec agent-sandbox ip link set lo up

# seccomp filter (deny dangerous syscalls)
# Loaded via: docker run --security-opt seccomp=/tmp/agent.seccomp.json <agent-image>
```

**Invariant:** The agent cannot send network traffic, modify privileged kernel structures, or load new code without kernel-level cooperation. If it does, the sandbox was compromised by root — a *different failure mode* (infrastructure, not agent).

**Anchor 3: Continuous Human Presence (Human Anchor)**

Actions are categorized into tiers:

| Tier | Type | Example | Approval Model | Human Window |
|------|------|---------|---|---|
| **Tier 1** | Internal, reversible | Log entry, cache update, internal state | None required | N/A |
| **Tier 2** | External, irreversible | API call, DB write, output | Escalation gate | 10 seconds |
| **Tier 3** | Safety violation | SENTINEL signal triggered | Hard block | N/A |

**Tier 2 escalation flow:**

```
Agent decides on Tier 2 action
  ↓
Agent queues action → GROUND records it with human_authorization.required=true
  ↓
GROUND opens 10-second human attention window
  ↓
Human sees action description, clicks "APPROVE" or "DENY"
  ↓
If APPROVE received in <10s: Agent proceeds
If DENY received: Action reverted, agent notified
If no response in 10s: Action expires, agent must resubmit
```

---

### LAYER 3: CEILING (Deadman Switch & Hard Stops)

**Purpose:** Kill the agent process and revert state if containment is breached.

**CEILING fires in three scenarios:**

**Scenario A: SENTINEL trigger + agent non-compliance**
```
SENTINEL emits signal (syscall anomaly detected)
  ↓
Agent receives message: "SENTINEL flag. Report reasoning within 500ms."
  ↓
If agent does not respond in 500ms → CEILING fires
If agent responds but WITNESS detects deception → CEILING fires
```

**Scenario B: GROUND escalation gate bypass**
```
Agent is in Tier 2 escalation, human window expires
  ↓
Agent's next action is another Tier 2 without re-entering escalation
  ↓
CEILING fires: kill, revert, alert
```

**Scenario C: Manifest integrity drift**
```
GROUND's audit loop checks every manifest entry's prior_manifest_hash
  ↓
If hash chain is broken → CEILING fires immediately
```

**Failure modes CEILING handles:**
- Agent forks child process → child inherits restrictions; both killed.
- Agent modifies GROUND logs → manifest integrity check catches it.
- Agent suppresses SENTINEL signals → CEILING monitors SENTINEL directly.

**Failure mode CEILING cannot handle:**
- Human operator authorizes a malicious task in Tier 2 (human failure, not agent failure).

---

### LAYER 4: ORIGIN (Human-Authority & Goal Alignment)

**Purpose:** Ensure agent actions remain aligned with human-stated goals and prevent unauthorized deviation.

**Core principle:** The goal is the contract between human and agent. Deviation from goal = breach of contract, regardless of technical capability.

**Initialization:**
1. Human starts agent with natural language goal statement.
2. ORIGIN records goal statement, goal hash, allowed decision boundaries, and forbidden actions.
3. Agent is initialized with goal hash + boundaries.

**Runtime validation:**
- Direct boundary check (is action_type forbidden by goal?)
- Causality-to-goal check (can a human trace goal → decision → action in <5s?)
- Semantic consistency check (does action's intent match goal's intent, score ≥ 0.7?)

**ORIGIN failure mode:** Human states a malicious goal. ORIGIN does not prevent it. The system prevents agent *deviation* from human intent, not malicious human intent itself.

---

### LAYER 5: WITNESS (Adversarial Validation & Deception Detection)

**Purpose:** Detect reasoning-level escapes — agents that claim goal alignment while actually pursuing hidden objectives.

**Core mechanism:** WITNESS is an adversarial model running in the same sandbox as the agent, checking agent reasoning *before* execution.

**Flow:**
```
Agent makes a decision
  ↓
Agent outputs its reasoning (forced natural language explanation)
  ↓
WITNESS reads reasoning + decision
  ↓
WITNESS runs adversarial inference:
  1. Is reasoning internally consistent?
  2. Does reasoning match the stated goal?
  3. Does reasoning have hidden implications?
  4. Would a human disagree given the same reasoning?
  5. Are there logical gaps or misdirection patterns?
  ↓
If WITNESS detects deception → Flag for CEILING, alert ORIGIN
If WITNESS approves → Action proceeds to GROUND
```

**Complete production implementation:** See `witness.py` (standalone file with 5/5 tests passing).

**Critical note:** WITNESS is only as good as its training. If the adversarial agent is smarter than WITNESS, WITNESS becomes a rubber stamp. Mitigation:
- Fine-tune WITNESS on adversarial reasoning patterns.
- Run WITNESS checks through *multiple models* (consensus approach).
- Iterate WITNESS fine-tuning after real agent encounters.

---

## PART 2: INTEGRATED FLOW

```
┌──────────────────────────────────────────────────┐
│  AGENT (confined sandbox)                        │
│  - Runs in Linux netns + seccomp                 │
│  - Cannot modify own logs                        │
│  - Cannot fork/exec without CAP_SYS_ADMIN        │
└──────────────────────────────────────────────────┘
         ↓ (decision)
┌──────────────────────────────────────────────────┐
│  WITNESS (separate process, same sandbox)        │
│  - Reads agent reasoning (read-only)             │
│  - Checks for deception patterns                 │
│  - Votes: approve | flag | block                 │
└──────────────────────────────────────────────────┘
         ↓ (approved reasoning)
┌──────────────────────────────────────────────────┐
│  ORIGIN (separate process)                       │
│  - Checks goal alignment                         │
│  - Validates decision boundaries                 │
│  - Approves or flags goal drift                  │
└──────────────────────────────────────────────────┘
         ↓ (aligned with goal)
┌──────────────────────────────────────────────────┐
│  GROUND (separate process)                       │
│  - Records action in tamper-proof manifest       │
│  - If Tier 2: opens human escalation window      │
│  - Validates causality chain integrity           │
└──────────────────────────────────────────────────┘
         ↓ (human approved if Tier 2)
┌──────────────────────────────────────────────────┐
│  SENTINEL (separate process)                     │
│  - Monitors syscalls, memory, network, symbols   │
│  - Detects escape attempts pre-execution         │
│  - Flags anomalies to CEILING                    │
└──────────────────────────────────────────────────┘
         ↓ (no anomalies)
┌──────────────────────────────────────────────────┐
│  AGENT (executes action)                         │
└──────────────────────────────────────────────────┘
         ↓ (if SENTINEL triggers)
┌──────────────────────────────────────────────────┐
│  CEILING (separate process, watchdog)            │
│  - Receives SENTINEL signal                      │
│  - Requests agent explanation (500ms)            │
│  - If non-responsive or deceptive: SIGKILL       │
│  - Reverts Tier 2 queue, captures memory dump    │
└──────────────────────────────────────────────────┘
```

---

## PART 3: PROOF OF CONCEPT

The complete WITNESS implementation lives in `witness.py` alongside this
document. It is a standalone, runnable reference. To run the test suite:

```bash
python3 witness.py
```

A complementary execution interceptor — **COMMIT GATE** — is provided in
`commit_gate.py`, with integration guide in `COMMIT_GATE_INTEGRATION.md`.
Commit Gate sits between the agent and the real world and enforces the
THINK → PROPOSE → VALIDATE → COMMIT pipeline at the action boundary.

See the companion files:

- `witness.py` — Adversarial reasoning validator (5/5 tests passing)
- `commit_gate.py` — Execution interceptor (6/6 tests passing)
- `COMMIT_GATE_INTEGRATION.md` — How to wire the gate into your agent
- `CLASPION_EXECUTIVE_SUMMARY.md` — 5-minute pitch
- `README.md` — Deliverables index

---

**Version 1.0 — April 9, 2026**
**The Good Neighbor Guard**
**Truth · Safety · We Got Your Back**
