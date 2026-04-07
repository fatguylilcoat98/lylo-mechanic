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

let apiCallCounter = 0;

class ApiClient {
  constructor(baseUrl = DEFAULT_BASE_URL) {
    this._baseUrl = baseUrl;
    this._instanceId = Date.now();
  }

  set baseUrl(url) {
    this._baseUrl = url;
  }

  _logState(label) {
    console.log(`[API ${label}] instanceId=${this._instanceId} baseUrl=${this._baseUrl}`);
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
    apiCallCounter++;
    const callId = apiCallCounter;
    const tag = `[API #${callId}]`;

    this._logState(tag);

    const url = `${this._baseUrl}/api/v1/quick/check`;
    const requestBody = JSON.stringify({input});

    console.log(tag, '===== REQUEST =====');
    console.log(tag, 'URL:', url);
    console.log(tag, 'Method: POST');
    console.log(tag, 'Body:', requestBody);
    console.log(tag, 'Body length:', requestBody.length);
    console.log(tag, 'Input type:', typeof input);
    console.log(tag, 'Input value:', JSON.stringify(input));

    let resp;
    const fetchOpts = {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: requestBody,
      signal: AbortSignal.timeout(30000), // 30s timeout — prevents hanging on stale connections
    };

    try {
      const fetchStart = Date.now();
      resp = await fetch(url, fetchOpts);
      const fetchDuration = Date.now() - fetchStart;

      console.log(tag, '===== RESPONSE =====');
      console.log(tag, 'Status:', resp.status, resp.statusText);
      console.log(tag, 'OK:', resp.ok);
      console.log(tag, 'Duration:', fetchDuration, 'ms');
      console.log(tag, 'Response type:', resp.type);
      console.log(tag, 'Response URL:', resp.url);
      console.log(tag, 'Headers:', JSON.stringify(Object.fromEntries(resp.headers?.entries?.() || [])));
    } catch (networkErr) {
      // Stale keep-alive connection — retry once with a fresh socket
      const isNetworkFail = networkErr.message?.includes('Network request failed')
        || networkErr.name === 'TimeoutError'
        || networkErr.name === 'AbortError';
      if (isNetworkFail) {
        console.warn(tag, `First attempt failed (${networkErr.message}), retrying once...`);
        try {
          const retryStart = Date.now();
          resp = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: requestBody,
            signal: AbortSignal.timeout(30000),
          });
          const retryDuration = Date.now() - retryStart;
          console.log(tag, `Retry succeeded in ${retryDuration}ms`);
        } catch (retryErr) {
          console.error(tag, '===== RETRY ALSO FAILED =====');
          console.error(tag, 'error.name:', retryErr.name);
          console.error(tag, 'error.message:', retryErr.message);
          console.error(tag, 'error.stack:', retryErr.stack);
          console.error(tag, 'Full error:', JSON.stringify(retryErr, Object.getOwnPropertyNames(retryErr)));
          console.error(tag, 'Request was:', requestBody);

          retryErr._lyloDebug = {
            callId,
            url,
            requestBody,
            phase: 'fetch_retry_threw',
            instanceId: this._instanceId,
          };
          throw retryErr;
        }
      } else {
        // Non-network error — don't retry
        console.error(tag, '===== FETCH THREW (no HTTP response) =====');
        console.error(tag, 'error.name:', networkErr.name);
        console.error(tag, 'error.message:', networkErr.message);
        console.error(tag, 'error.code:', networkErr.code);
        console.error(tag, 'error.type:', networkErr.type);
        console.error(tag, 'error.cause:', networkErr.cause);
        console.error(tag, 'error.stack:', networkErr.stack);
        console.error(tag, 'Full error:', JSON.stringify(networkErr, Object.getOwnPropertyNames(networkErr)));
        console.error(tag, 'Request was:', requestBody);

        networkErr._lyloDebug = {
          callId,
          url,
          requestBody,
          phase: 'fetch_threw',
          instanceId: this._instanceId,
        };
        throw networkErr;
      }
    }

    // We got an HTTP response — read the body
    let responseText;
    try {
      responseText = await resp.text();
      console.log(tag, 'Response body:', responseText.slice(0, 1000));
    } catch (bodyErr) {
      console.error(tag, 'Failed to read response body:', bodyErr.message);
      responseText = `(body unreadable: ${bodyErr.message})`;
    }

    if (!resp.ok) {
      console.error(tag, '===== HTTP ERROR =====');
      console.error(tag, 'Status:', resp.status, resp.statusText);
      console.error(tag, 'Body:', responseText.slice(0, 500));
      console.error(tag, 'Request was:', requestBody);

      const err = new Error(`Quick check failed (${resp.status}): ${responseText}`);
      err._lyloDebug = {
        callId,
        url,
        requestBody,
        status: resp.status,
        statusText: resp.statusText,
        responseBody: responseText,
        phase: 'http_error',
        instanceId: this._instanceId,
      };
      throw err;
    }

    // Parse JSON from the already-read text
    try {
      const parsed = JSON.parse(responseText);
      console.log(tag, 'Parsed OK — keys:', Object.keys(parsed));
      return parsed;
    } catch (jsonErr) {
      console.error(tag, '===== JSON PARSE FAILED =====');
      console.error(tag, 'Raw text:', responseText.slice(0, 500));
      jsonErr._lyloDebug = {callId, url, requestBody, responseBody: responseText, phase: 'json_parse'};
      throw jsonErr;
    }
  }

  /**
   * Quick Check from OBD scan data — extracts DTCs from a fullScan() result
   * and sends them through the quick-check MVP endpoint.
   *
   * @param {object} scanData - Result from OBDService.fullScan()
   * @returns {object} Quick check results with ShopScript
   */
  async quickCheckFromScan(scanData) {
    const tag = `[API quickCheckFromScan]`;
    console.log(tag, 'Called with scanData type:', typeof scanData);
    console.log(tag, 'scanData is null:', scanData === null);
    console.log(tag, 'scanData is undefined:', scanData === undefined);
    console.log(tag, 'raw_dtcs:', JSON.stringify(scanData?.raw_dtcs));

    const dtcCodes = (scanData?.raw_dtcs || []).map(d => d?.code).filter(Boolean);
    console.log(tag, 'Extracted DTC codes:', JSON.stringify(dtcCodes));

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
