/**
 * ApiClient — Talks to the LYLO Mechanic Flask backend.
 *
 * The backend runs the full 12-layer diagnostic pipeline:
 * normalization → confidence → hypothesis → safety → DIY → cost → veracore
 *
 * This client sends raw OBD data and receives a MechanicResponse.
 */

// Default to local development. Change for production.
const DEFAULT_BASE_URL = 'http://10.0.2.2:5050'; // Android emulator → host machine

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
