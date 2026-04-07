/**
 * ApiClient — Talks to the LYLO Mechanic Flask backend.
 *
 * The backend runs the full 12-layer diagnostic pipeline:
 * normalization → confidence → hypothesis → safety → DIY → cost → veracore
 *
 * This client sends raw OBD data and receives a MechanicResponse.
 */

// Production backend on Render
const DEFAULT_BASE_URL = 'https://lylo-mechanic.onrender.com';

class ApiClient {
  constructor(baseUrl = DEFAULT_BASE_URL) {
    this._baseUrl = baseUrl;
  }

  set baseUrl(url) {
    this._baseUrl = url;
  }

  /**
   * Send live OBD scan data to the backend for full diagnosis.
   *
   * @param {object} scanData - OBDSessionInput from OBDService.fullScan()
   * @param {object} vehicle  - Vehicle profile {year, make, model, engine, odometer}
   * @param {array}  symptoms - Optional user-reported symptoms
   * @returns {object} MechanicResponse from the backend
   */
  async diagnose(scanData, vehicle, symptoms = []) {
    const payload = {
      vehicle: {
        year: vehicle.year || 0,
        make: vehicle.make || 'Unknown',
        model: vehicle.model || 'Unknown',
        engine: vehicle.engine || '',
        odometer: vehicle.odometer || 0,
        is_ev: vehicle.is_ev || false,
        is_hybrid: vehicle.is_hybrid || false,
      },
      obd_session: scanData,
      symptoms: symptoms,
    };

    const resp = await fetch(`${this._baseUrl}/api/v1/diagnose/live`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Backend error (${resp.status}): ${text}`);
    }

    return resp.json();
  }

  /**
   * Run a demo scenario on the backend (for testing without hardware).
   */
  async diagnoseScenario(scenarioId) {
    const resp = await fetch(
      `${this._baseUrl}/api/v1/diagnose/scenario/${scenarioId}`,
      {method: 'POST'},
    );

    if (!resp.ok) {
      throw new Error(`Scenario ${scenarioId} failed: ${resp.status}`);
    }

    return resp.json();
  }

  /**
   * Get the list of available demo scenarios.
   */
  async getScenarios() {
    const resp = await fetch(`${this._baseUrl}/api/v1/scenarios/list`);
    if (!resp.ok) throw new Error('Failed to fetch scenarios');
    return resp.json();
  }

  /**
   * Quick Check MVP — send DTC codes or symptom text to the new quick-check endpoint.
   * Returns ShopScript-ready results: what's wrong, urgency, cost, difficulty,
   * what to say at the shop, and red flags.
   *
   * @param {string} input - A DTC code ("P0420"), multiple codes ("P0420 P0171"),
   *                         or symptom text ("rough idle, check engine light")
   * @returns {object} {input, input_type, results: [{code, whats_wrong, urgency, cost, difficulty, shop_script, red_flags}]}
   */
  async quickCheck(input) {
    const resp = await fetch(`${this._baseUrl}/api/v1/quick/check`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({input}),
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Quick check failed (${resp.status}): ${text}`);
    }

    return resp.json();
  }

  /**
   * Quick Check from OBD scan data — extracts DTCs from a fullScan() result
   * and sends them through the quick-check MVP endpoint.
   *
   * @param {object} scanData - Result from OBDService.fullScan()
   * @returns {object} Quick check results with ShopScript
   */
  async quickCheckFromScan(scanData) {
    const dtcCodes = (scanData.raw_dtcs || []).map(d => d.code).filter(Boolean);

    if (dtcCodes.length === 0) {
      // No codes found — return a helpful "clean" result
      return {
        input: 'OBD Scan (no codes)',
        input_type: 'obd_scan',
        results: [{
          code: 'NO CODES',
          whats_wrong: {
            summary: 'No diagnostic trouble codes found.',
            explanation: 'Your vehicle\'s computer has no stored fault codes. If you\'re experiencing symptoms, they may not have triggered a code yet.',
            check_first: [
              'If the check engine light is on but no codes found, codes may have been recently cleared',
              'Some issues (brakes, tires, suspension) don\'t trigger OBD codes',
              'If symptoms persist, describe them for a symptom-based check',
            ],
          },
          urgency: {
            level: 'SAFE TO DRIVE',
            color: 'green',
            message: 'No fault codes detected. If you\'re experiencing symptoms, get a visual inspection.',
          },
          cost: {diy: 'N/A', shop: '$0 – $100 (inspection)', note: 'A basic inspection is typically free or low cost.'},
          difficulty: {level: 'N/A', label: 'No repair needed based on codes', icon: 'check'},
          shop_script: '"I had my car scanned and no codes came up, but I\'m noticing [describe symptom]. Can you do a visual inspection and let me know if you see anything? I\'d like a written estimate before any work is done."',
          red_flags: [
            'If a shop says they need to run expensive diagnostics when there are no codes, ask what specifically they\'re testing for.',
            'Don\'t let anyone upsell you on repairs when there are no fault codes unless they can show you the problem.',
          ],
        }],
      };
    }

    // Send all DTCs as a single input string
    const input = dtcCodes.join(' ');
    return this.quickCheck(input);
  }

  /**
   * Health check — is the backend running?
   */
  async ping() {
    try {
      const resp = await fetch(`${this._baseUrl}/api/v1/session/ping`, {
        signal: AbortSignal.timeout(3000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }
}

export default new ApiClient();
