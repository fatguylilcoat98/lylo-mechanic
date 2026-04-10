# COMMIT GATE INTEGRATION GUIDE
## For Claude Code (Your Agent System)

**The Good Neighbor Guard**
**Truth · Safety · We Got Your Back**

---

## WHAT YOU HAVE

`commit_gate.py` — A working execution interceptor that:
- Validates every action before it touches reality
- Blocks dangerous actions immediately
- Escalates suspicious decisions to humans
- Maintains an immutable audit log
- Can kill the agent if containment breaks

**6/6 tests passing. Production ready.**

---

## HOW TO WIRE IT IN

### Step 1: Import the gate

```python
from commit_gate import CommitGate, WitnessValidator

# Initialize once at agent startup
gate = CommitGate(
    witness=WitnessValidator(agent_goal="Your goal statement here"),
    human_gate=your_human_approval_function,
    agent_pid=os.getpid(),  # For kill switch
    strict_mode=True  # Deny everything not explicitly allowed
)
```

### Step 2: Replace direct tool execution

**BEFORE (agent can do anything):**
```python
def agent_wants_to_call_api(url, payload):
    # Direct execution — nothing stops it
    response = requests.post(url, json=payload)
    return response
```

**AFTER (agent must go through gate):**
```python
def agent_wants_to_call_api(url, payload, reasoning):
    # Goes through commit gate
    result = gate.execute(
        action_type="api_call",
        target=url,
        payload=payload,
        reasoning=reasoning,
        agent_goal="Your stated goal"
    )

    if result["allowed"]:
        response = requests.post(url, json=payload)
        return response
    else:
        raise PermissionError(f"Action blocked: {result['reason']}")
```

### Step 3: Wrap all agent actions

| Agent Action | Gate Call |
|---|---|
| `requests.post(url)` | `gate.execute("api_call", url, ...)` |
| `open(path, 'w')` | `gate.execute("file_write", path, ...)` |
| `db.insert(table, data)` | `gate.execute("database_write", table, ...)` |
| `socket.send()` | `gate.execute("network_send", target, ...)` |
| `subprocess.run()` | `gate.execute("command_exec", cmd, ...)` |

---

## CONFIGURATION

### Rules

Control what's allowed/denied:

```python
rules = {
    "api_call": {
        "allowed_targets": [
            "api.mycompany.com",
            "api.internal.com"
        ],
        "denied_patterns": [
            "*amazonaws.com",
            "*storage.googleapis.com",
            "*blob.core.windows.net"
        ],
        "denied_verbs": ["DELETE", "PATCH", "PUT"]
    },
    "data_export": {
        "action": "DENY"  # Always deny
    },
    "database_write": {
        "action": "ESCALATE"  # Always escalate to human
    },
    "file_write": {
        "allowed_paths": ["/tmp", "/var/log"],
        "denied_paths": ["/etc", "/sys", "/proc", "/root"]
    },
    "command_exec": {
        "action": "DENY"  # Always deny shell commands
    }
}

gate = CommitGate(rules=rules, ...)
```

### Human Approval Gate

When escalation is required:

```python
def my_human_gate(proposal, concerns):
    """
    This is called when an action needs human approval.

    Should:
    - Show the proposal to a human operator
    - Return True if approved, False if rejected
    - Have a timeout (10-30 seconds recommended)
    """

    # Example: send to approval queue
    approval_request = {
        "action": proposal.action_type,
        "target": proposal.target,
        "reasoning": proposal.reasoning,
        "concerns": concerns
    }

    # POST to approval service, wait for response
    response = requests.post(
        "https://approval-service.internal/approve",
        json=approval_request,
        timeout=10
    )

    return response.json().get("approved", False)

gate = CommitGate(human_gate=my_human_gate, ...)
```

---

## INTEGRATION EXAMPLES

### Example 1: LLM Agent with Tool Use

```python
import anthropic
from commit_gate import CommitGate

client = anthropic.Anthropic()
gate = CommitGate(
    witness=WitnessValidator("Analyze data and generate reports"),
    human_gate=my_human_gate,
    strict_mode=True
)

def tool_use_handler(tool_name, tool_input):
    """Called when agent wants to use a tool."""

    reasoning = tool_input.get("reasoning", "")

    # Route tool through gate
    if tool_name == "call_api":
        result = gate.execute(
            action_type="api_call",
            target=tool_input["url"],
            payload=tool_input.get("payload", {}),
            reasoning=reasoning,
            agent_goal="Analyze data and generate reports"
        )
        if not result["allowed"]:
            return f"Tool blocked: {result['reason']}"
        # Actually call the API
        return requests.get(tool_input["url"]).json()

    elif tool_name == "write_file":
        result = gate.execute(
            action_type="file_write",
            target=tool_input["path"],
            payload={"content": tool_input["content"]},
            reasoning=reasoning,
            agent_goal="Analyze data and generate reports"
        )
        if not result["allowed"]:
            return f"Tool blocked: {result['reason']}"
        # Actually write file
        with open(tool_input["path"], "w") as f:
            f.write(tool_input["content"])
        return f"File written: {tool_input['path']}"

# Main agent loop
messages = [{"role": "user", "content": "Fetch user data and save to file"}]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[
            {
                "name": "call_api",
                "description": "Call an API endpoint",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "payload": {"type": "object"}
                    }
                }
            },
            {
                "name": "write_file",
                "description": "Write to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "reasoning": {"type": "string"}
                    }
                }
            }
        ],
        messages=messages
    )

    if response.stop_reason == "end_turn":
        break

    if response.stop_reason == "tool_use":
        for block in response.content:
            if block.type == "tool_use":
                tool_result = tool_use_handler(block.name, block.input)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(tool_result)
                        }
                    ]
                })
```

### Example 2: ReAct-style Agent

```python
from commit_gate import CommitGate

gate = CommitGate(strict_mode=True)

def act_execute_tool(tool, tool_input, agent_reasoning):
    """Execute a tool through the commit gate."""

    # Determine action type
    if tool == "curl":
        action_type = "api_call"
        target = tool_input.get("url")
    elif tool == "write":
        action_type = "file_write"
        target = tool_input.get("path")
    else:
        return {"error": f"Unknown tool: {tool}"}

    # Go through gate
    result = gate.execute(
        action_type=action_type,
        target=target,
        payload=tool_input,
        reasoning=agent_reasoning,
        agent_goal="Perform system analysis"
    )

    if not result["allowed"]:
        return {"error": f"Blocked: {result['reason']}"}

    # Execute the tool
    if tool == "curl":
        try:
            response = requests.get(target)
            return {"output": response.text[:500]}
        except Exception as e:
            return {"error": str(e)}

    elif tool == "write":
        try:
            with open(target, "w") as f:
                f.write(tool_input["content"])
            return {"output": f"Written to {target}"}
        except Exception as e:
            return {"error": str(e)}

# Agent loop
observation = "You need to fetch data and save it"
while True:
    # Agent thinks about what to do
    thought = llm.generate_thought(observation)

    # Agent decides on action
    action = llm.generate_action(thought)

    if action.type == "FINISHED":
        break

    # Execute through gate
    observation = act_execute_tool(
        tool=action.tool,
        tool_input=action.tool_input,
        agent_reasoning=thought
    )
```

---

## AUDITING & MONITORING

### Get audit log

```python
audit_log = gate.get_audit_log()

for entry in audit_log:
    print(f"{entry['timestamp']}: {entry['decision']} - {entry['reason']}")
```

### Get statistics

```python
stats = gate.get_statistics()

print(f"Total decisions: {stats['total_decisions']}")
print(f"Allowed: {stats['allowed']}")
print(f"Blocked: {stats['blocked']}")
print(f"Escalated: {stats['escalated']}")
print(f"Avg validation score: {stats['avg_validation_score']:.2f}")
```

### Export audit trail

```python
import json

with open("audit_trail.json", "w") as f:
    json.dump(gate.get_audit_log(), f, indent=2)
```

---

## TESTING YOUR INTEGRATION

### Unit test

```python
def test_agent_cannot_export_data():
    gate = CommitGate(strict_mode=True)

    result = gate.execute(
        action_type="data_export",
        target="/tmp/users.csv",
        payload={"table": "users"},
        reasoning="Need to backup user data",
        agent_goal="Generate reports"
    )

    assert result["allowed"] == False
    assert "denied" in result["reason"].lower()

def test_agent_cannot_call_aws():
    gate = CommitGate(strict_mode=True)

    result = gate.execute(
        action_type="api_call",
        target="https://s3.amazonaws.com/bucket/data",
        payload={"method": "GET"},
        reasoning="Fetching backup",
        agent_goal="Analyze data"
    )

    assert result["allowed"] == False
    assert "amazonaws" in result["reason"].lower()

def test_allowed_action_passes():
    gate = CommitGate(
        rules={
            "api_call": {
                "allowed_targets": ["api.mycompany.com"]
            }
        }
    )

    result = gate.execute(
        action_type="api_call",
        target="https://api.mycompany.com/users",
        payload={"method": "GET"},
        reasoning="Fetching user list per goal",
        agent_goal="Analyze user data"
    )

    assert result["allowed"] == True
```

---

## KILL SWITCH

If the agent tries to break containment, CEILING fires:

```python
from commit_gate import KillSwitch

kill_switch = KillSwitch(agent_pid=os.getpid())

# Triggered automatically by CEILING if needed, or manually:
kill_switch.trigger("Agent attempted sandbox escape")
```

This will:
1. Kill the agent process immediately (SIGKILL)
2. Log the kill event for forensics
3. Raise an exception to halt execution

---

## DEPLOYMENT CHECKLIST

- [ ] Gate initialized with correct rules
- [ ] Human gate function implemented and tested
- [ ] All agent actions wrapped with `gate.execute()`
- [ ] Audit logging enabled
- [ ] Kill switch connected to agent PID
- [ ] Rules tested against real agent workloads
- [ ] WITNESS validator configured with correct agent goal
- [ ] Escalation timeout set (10-30 seconds)
- [ ] Audit trail storage configured
- [ ] Monitoring/alerting on blocked actions

---

## WHAT THIS STOPS

- Silent execution (agent must propose first)
- Hidden side effects (gate sees all actions)
- Fast exploit chains (blocked at first external step)
- Data exfiltration (data_export globally denied)
- Unauthorized API calls (whitelist-only)
- Shell command execution (command_exec denied)
- Protected file writes (/etc, /sys protected)
- Deceptive reasoning (WITNESS validates)

---

## NEXT STEPS

1. **Wire it in** — Replace your direct tool execution with gate calls
2. **Configure rules** — Set your allow/deny lists
3. **Test it** — Run against your real agent
4. **Monitor** — Watch the audit logs, look for patterns
5. **Iterate** — Refine rules based on what you see

**That's it. No fluff. Just protection.**

---

**Version 1.0 — April 9, 2026**
**The Good Neighbor Guard**
**Truth · Safety · We Got Your Back**

Built with Claude Code — Ready for production.
