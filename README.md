# LYLO Mechanic
## The Good Neighbor Guard
### Christopher Hughes · Sacramento, CA
### AI Collaborators: Claude · GPT · Gemini · Groq
### Truth · Safety · We Got Your Back

---

## What This Is

A fully working vehicle diagnostics demo system built on top of OBDLink-style data.
Not a chatbot. A structured multi-hypothesis diagnostic engine with:

- Safety escalation matrix (6 levels, hard logic)
- DIY eligibility gate (hard blocks enforced)
- Multi-hypothesis confidence engine
- Cost estimates (DIY / Shop / Dealer)
- Veracore truth challenge layer
- Handshake enforcement on risky decisions
- 10 demo scenarios covering every edge case

---

## FILE STRUCTURE

```
lylo_mechanic/
├── backend/
│   ├── app.py                          ← Flask entry point
│   ├── models/schemas.py               ← All data schemas
│   ├── api/
│   │   ├── orchestrator.py             ← Main pipeline (all 12 layers)
│   │   └── routes/
│   │       ├── diagnose.py             ← POST /diagnose/scenario/<id>
│   │       ├── scenarios.py            ← GET /scenarios/list
│   │       ├── session.py              ← GET /session/ping
│   │       └── tutorial.py             ← GET /tutorial/<cause_id>
│   ├── normalization/normalizer.py     ← Raw OBD → VehicleState
│   ├── confidence/confidence_engine.py ← DataConfidence computation
│   ├── diagnosis/hypothesis_engine.py  ← Multi-cause ranked diagnosis
│   ├── safety/safety_classifier.py     ← Safety escalation matrix
│   ├── diy/eligibility_gate.py         ← DIY gate + hard blocks
│   ├── cost/cost_engine.py             ← Cost estimates
│   ├── veracore/truth_check.py         ← Challenge/flag weak claims
│   ├── demo_scenarios/scenarios.py     ← 10 test scenarios
│   └── data/
│       ├── dtc_db/dtc_codes.json       ← SAE DTC database
│       ├── hypothesis_rules/cause_map.json  ← Cause logic per DTC
│       └── pricing/repair_costs.json   ← Cost data
└── frontend/
    └── templates/index.html            ← Full UI (single file)
```

---

## RUN INSTRUCTIONS

### 1. Install dependencies
```bash
cd lylo_mechanic
pip install flask flask-cors
```

### 2. Start the server
```bash
cd backend
python app.py
```

Server runs at: **http://localhost:5050**

### 3. Open the UI
Navigate to **http://localhost:5050** in your browser.

---

## DEMO INSTRUCTIONS

1. Open http://localhost:5050
2. Click any scenario in the left sidebar
3. Watch the scan animation (simulates OBDLink read)
4. Review full diagnostic output:
   - Vehicle identity + scan confidence
   - Safety classification (color-coded, hard logic)
   - Ranked hypotheses (expandable, with confidence + evidence)
   - Cost comparison (DIY / Shop / Dealer)
   - Repair path + DIY eligibility
   - Tutorial gate (locked/unlocked with reason)
   - Veracore truth flags
   - Handshake enforcement

### Key scenarios to demo in order:
1. **P0420 — Not What It Seems** — shows multi-hypothesis, $1200 mistake avoided
2. **Flashing Misfire** — TOW RECOMMENDED, tutorial blocked, handshake required
3. **No Codes — Brake Danger** — DO NOT DRIVE from symptom alone, clean OBD
4. **Overheating** — EMERGENCY, full lockdown
5. **Low Voltage Cascade** — 5 hypotheses, weak battery is root cause
6. **Cleared Codes** — confidence degraded, monitors incomplete warning

---

## API ENDPOINTS

```
GET  /health                                   → system health
GET  /api/v1/scenarios/list                    → list all 10 scenarios
POST /api/v1/diagnose/scenario/<scenario_id>   → run full diagnosis
GET  /api/v1/session/ping                      → adapter status
GET  /api/v1/tutorial/<cause_id>               → tutorial gate check
```

---

## STUBBED / SIMULATED AREAS

| Area | Status | Notes |
|------|--------|-------|
| OBDLink hardware connection | SIMULATED | Real OBDLink BLE/WiFi protocol replaces `OBDSessionInput` |
| Live PID streaming | SIMULATED | Demo uses static scenario data |
| Tutorial content library | GATE IS LIVE, CONTENT STUB | Gate logic enforced; content library is Phase 5 |
| Handshake persistence | UI ONLY | Full Handshake backend integration is separate service |
| Veracore API call | EMBEDDED LOGIC | Currently local; can route to veracore.onrender.com |
| Pricing data refresh | STATIC FILE | Phase 7: connect to live pricing API |

---

## NEXT INTEGRATION STEPS

### Step 1 — Wire real OBDLink hardware
Replace `OBDSessionInput` construction in `demo_scenarios/scenarios.py` with
actual OBDLink SDK data. The `OBDSessionInput` schema accepts everything the
hardware returns. No pipeline changes needed.

### Step 2 — Connect to Veracore
In `veracore/truth_check.py`, route flagging through the Veracore API at
`veracore.onrender.com` instead of local logic. The schema is already compatible.

### Step 3 — Connect to Handshake service
In `orchestrator.py`, replace `_evaluate_handshake()` with a call to
`the-handshake.onrender.com` using the existing Handshake boundary protocol.

### Step 4 — Expand DTC database
Add make/model specific manufacturer codes to `data/dtc_db/dtc_codes.json`.
The normalizer already handles unknown codes gracefully.

### Step 5 — Build tutorial content library
Each tutorial is a JSON file in `data/tutorials_content/`.
The gate in `orchestrator.py` is already enforcing all rules.
Content only flows through if safety + DIY gate approve it.

### Step 6 — Deploy
The Flask app is production-ready with gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5050 app:app
```
Deploy to Render, Railway, or any Python host.

---

## SAFETY GUARANTEE

The safety matrix and DIY gate are PURE FUNCTIONS with no AI involved.
They cannot be overridden. Emergency and DO NOT DRIVE states always block tutorials.
Hard-block repairs are hardcoded constants — no LLM can change them.

This is by design. The Good Neighbor Guard principle:
**Truth · Safety · We Got Your Back**
