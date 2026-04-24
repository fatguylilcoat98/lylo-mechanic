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

function _makeTimeoutSignal(ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

let apiCallCounter = 0;

class ApiClient {
  constructor(baseUrl = DEFAULT_BASE_URL) {
    this._baseUrl = baseUrl;
    this._instanceId = Date.now();
    this._authToken = null;
  }

  set baseUrl(url) {
    this._baseUrl = url;
  }

  /**
   * Set the Supabase JWT token for authenticated requests.
   * Call this after the user logs in via Supabase.
   * @param {string|null} token - JWT access token from Supabase session
   */
  setAuthToken(token) {
    this._authToken = token;
    console.log('[ApiClient] Auth token', token ? 'set' : 'cleared');
  }

  /**
   * Build headers including auth token if available.
   */
  _headers(extra = {}) {
    const headers = {'Content-Type': 'application/json', ...extra};
    if (this._authToken) {
      headers['Authorization'] = `Bearer ${this._authToken}`;
    }
    return headers;
  }

  _logState(label) {
    console.log(`[API ${label}] instanceId=${this._instanceId} baseUrl=${this._baseUrl} authed=${!!this._authToken}`);
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
      headers: this._headers(),
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
      {
        method: 'POST',
        headers: this._headers(),
      },
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
      headers: this._headers(),
      body: requestBody,
    };

    const {signal, clear} = _makeTimeoutSignal(30000);
    try {
      const fetchStart = Date.now();
      resp = await fetch(url, {...fetchOpts, signal});
      clear();
      const fetchDuration = Date.now() - fetchStart;

      console.log(tag, '===== RESPONSE =====');
      console.log(tag, 'Status:', resp.status, resp.statusText);
      console.log(tag, 'OK:', resp.ok);
      console.log(tag, 'Duration:', fetchDuration, 'ms');
      console.log(tag, 'Response type:', resp.type);
      console.log(tag, 'Response URL:', resp.url);
      console.log(tag, 'Headers:', JSON.stringify(Object.fromEntries(resp.headers?.entries?.() || [])));
    } catch (networkErr) {
      const isNetworkFail = networkErr.message?.includes('Network request failed')
        || networkErr.name === 'TimeoutError'
        || networkErr.name === 'AbortError';
      if (isNetworkFail) {
        console.warn(tag, `First attempt failed (${networkErr.message}), retrying once...`);
        try {
          const retryStart = Date.now();
          const {signal: retrySignal, clear: retryClear} = _makeTimeoutSignal(30000);
          try {
            resp = await fetch(url, {
              method: 'POST',
              headers: this._headers(),
              body: requestBody,
              signal: retrySignal,
            });
          } finally {
            retryClear();
          }
          const retryDuration = Date.now() - retryStart;
          console.log(tag, `Retry succeeded in ${retryDuration}ms`);
        } catch (retryErr) {
          console.error(tag, '===== RETRY ALSO FAILED =====');
          console.error(tag, 'error.name:', retryErr.name);
          console.error(tag, 'error.message:', retryErr.message);
          console.error(tag, 'error.stack:', retryErr.stack);
          retryErr._lyloDebug = {
            callId, url, requestBody,
            phase: 'fetch_retry_threw',
            instanceId: this._instanceId,
          };
          throw retryErr;
        }
      } else {
        console.error(tag, '===== FETCH THREW (no HTTP response) =====');
        console.error(tag, 'error.name:', networkErr.name);
        console.error(tag, 'error.message:', networkErr.message);
        networkErr._lyloDebug = {
          callId, url, requestBody,
          phase: 'fetch_threw',
          instanceId: this._instanceId,
        };
        throw networkErr;
      }
    }

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

      const err = new Error(`Quick check failed (${resp.status}): ${responseText}`);
      err._lyloDebug = {
        callId, url, requestBody,
        status: resp.status,
        statusText: resp.statusText,
        responseBody: responseText,
        phase: 'http_error',
        instanceId: this._instanceId,
      };
      throw err;
    }

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
   * Unified Analysis — single endpoint for ALL diagnostics.
   */
  async analyze(params) {
    apiCallCounter++;
    const callId = apiCallCounter;
    const tag = `[API ANALYZE #${callId}]`;

    const url = `${this._baseUrl}/api/v1/analyze`;
    const requestBody = JSON.stringify(params);

    console.log(tag, 'URL:', url);
    console.log(tag, 'Source:', params.source);
    console.log(tag, 'Body:', requestBody.slice(0, 300));

    let resp;
    const fetchOpts = {
      method: 'POST',
      headers: this._headers(),
      body: requestBody,
    };

    const {signal, clear} = _makeTimeoutSignal(30000);
    try {
      resp = await fetch(url, {...fetchOpts, signal});
      clear();
    } catch (networkErr) {
      const isNetworkFail = networkErr.message?.includes('Network request failed')
        || networkErr.name === 'TimeoutError';
      if (isNetworkFail) {
        console.warn(tag, 'Retrying analyze...');
        const {signal: retrySignal, clear: retryClear} = _makeTimeoutSignal(30000);
        try {
          resp = await fetch(url, {
            method: 'POST',
            headers: this._headers(),
            body: requestBody,
            signal: retrySignal,
          });
        } finally {
          retryClear();
        }
      } else {
        throw networkErr;
      }
    }

    const responseText = await resp.text();

    if (!resp.ok) {
      if (resp.status === 403 || resp.status === 429) {
        return JSON.parse(responseText);
      }
      throw new Error(`Analyze failed (${resp.status}): ${responseText}`);
    }

    return JSON.parse(responseText);
  }

  /**
   * Analyze from OBD scan data — sends codes through unified endpoint.
   */
  async quickCheckFromScan(scanData, vehicle = null) {
    // Wait for BT to settle before network call
    await new Promise(resolve => setTimeout(resolve, 2000));

    const tag = `[API quickCheckFromScan]`;
    console.log(tag, 'raw_dtcs:', JSON.stringify(scanData?.raw_dtcs));

    const dtcCodes = (scanData?.raw_dtcs || []).map(d => d?.code).filter(Boolean);
    console.log(tag, 'Extracted DTC codes:', JSON.stringify(dtcCodes));

    if (dtcCodes.length === 0) {
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

    return this.analyze({
      source: 'obd',
      codes: dtcCodes,
      raw_dtcs: scanData?.raw_dtcs,
      vehicle: vehicle ? `${vehicle.year} ${vehicle.make} ${vehicle.model}`.trim() : undefined,
    });
  }

  /**
   * Health check — is the backend running?
   */
  async ping() {
    const {signal, clear} = _makeTimeoutSignal(3000);
    try {
      const resp = await fetch(`${this._baseUrl}/api/v1/session/ping`, {
        signal,
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      clear();
    }
  }
}

export default new ApiClient();
