/*
 * LYLO Mechanic — OBDService
 *
 * OBD-II / ELM327 domain logic. Lives on top of BluetoothService +
 * AdapterSession. This file does NOT own the transport, the buffer,
 * the queue, or the parser — those all live in obd/session.js.
 *
 * What OBDService owns:
 *   - Init sequence (delegated to session.initialize())
 *   - PID definitions and parsing formulas
 *   - DTC decoding (Mode 03 / 07)
 *   - VIN read (Mode 09 PID 02) and NHTSA VIN decode
 *   - fullScan() — the high-level "scan the car" routine
 */

import BluetoothService from './BluetoothService';
import { extractHexBytes } from './obd/parser';

// Mode 01 PID definitions. parse() receives an int[] of data bytes.
const PID_DEFS = {
  '05': { name: 'coolant_temp',     unit: 'F',   parse: b => (b[0] - 40) * 9 / 5 + 32 },
  '0C': { name: 'rpm',              unit: 'RPM', parse: b => (b[0] * 256 + b[1]) / 4 },
  '0D': { name: 'vehicle_speed',    unit: 'mph', parse: b => Math.round(b[0] * 0.621371) },
  '42': { name: 'battery_voltage',  unit: 'V',   parse: b => (b[0] * 256 + b[1]) / 1000 },
  '06': { name: 'short_fuel_trim_1',unit: '%',   parse: b => (b[0] - 128) * 100 / 128 },
  '07': { name: 'long_fuel_trim_1', unit: '%',   parse: b => (b[0] - 128) * 100 / 128 },
  '0F': { name: 'intake_air_temp',  unit: 'F',   parse: b => (b[0] - 40) * 9 / 5 + 32 },
  '10': { name: 'maf_flow',         unit: 'g/s', parse: b => (b[0] * 256 + b[1]) / 100 },
  '11': { name: 'throttle_pos',     unit: '%',   parse: b => b[0] * 100 / 255 },
};

const SCAN_PIDS = ['05', '0C', '0D', '42', '06', '07', '0F', '10', '11'];

const MONITOR_NAMES = [
  'misfire', 'fuel_system', 'components', 'catalyst',
  'heated_catalyst', 'evap_system', 'secondary_air',
  'ac_refrigerant', 'oxygen_sensor', 'oxygen_sensor_heater',
  'egr_system',
];

class OBDService {
  constructor() {
    this._initialized = false;
    this._protocol = null;
    this._adapterId = null;
  }

  get initialized() { return this._initialized; }
  get protocol() { return this._protocol; }
  get adapterId() { return this._adapterId; }

  // ── Initialization ─────────────────────────────────────────────
  // Delegates to the session's initialize() which runs the full
  // ATZ/ATE0/ATL0/ATS0/ATH0/ATSP0 sequence with per-command timeouts.
  async initialize() {
    try {
      const info = await BluetoothService.initializeSession();
      this._adapterId = info.adapter;
      this._protocol = info.protocol;

      // Probe: 0100 to force protocol detection. A few adapters need
      // this before ATDPN returns a useful answer.
      try {
        await BluetoothService.sendCommand('0100', { timeoutMs: 8000 });
      } catch (e) {
        console.warn('[OBD] 0100 probe failed (non-fatal): ' + e.message);
      }

      this._initialized = true;
      return {
        adapter: this._adapterId || 'unknown',
        protocol: this._protocol || 'auto',
      };
    } catch (err) {
      this._initialized = false;
      throw new Error('Adapter initialization failed: ' + err.message);
    }
  }

  // ── PID read ───────────────────────────────────────────────────
  async readPID(pid) {
    const def = PID_DEFS[pid];
    if (!def) return null;
    try {
      const parsed = await BluetoothService.sendCommand('01' + pid);
      if (!parsed.ok) return null;
      const bytes = extractHexBytes(parsed, '41', pid);
      if (!bytes || bytes.length === 0) return null;
      return {
        pid,
        name: def.name,
        value: Math.round(def.parse(bytes) * 100) / 100,
        unit: def.unit,
      };
    } catch (e) {
      console.warn('[OBD] readPID ' + pid + ' failed: ' + e.message);
      return null;
    }
  }

  // ── Monitor status (Mode 01 PID 01) ────────────────────────────
  async readMonitorStatus() {
    try {
      const parsed = await BluetoothService.sendCommand('0101');
      if (!parsed.ok) return { milOn: false, dtcCount: 0, monitors: {} };
      const bytes = extractHexBytes(parsed, '41', '01');
      if (!bytes || bytes.length < 4) {
        return { milOn: false, dtcCount: 0, monitors: {} };
      }
      const milOn = (bytes[0] & 0x80) !== 0;
      const dtcCount = bytes[0] & 0x7F;
      const monitors = {};
      const testAvail = bytes[1];
      const testIncomplete = bytes[2];
      MONITOR_NAMES.forEach((name, i) => {
        if (i < 8) {
          const bit = 1 << i;
          if (testAvail & bit) {
            monitors[name] = (testIncomplete & bit) ? 'incomplete' : 'complete';
          }
        }
      });
      return { milOn, dtcCount, monitors };
    } catch (e) {
      console.warn('[OBD] readMonitorStatus failed: ' + e.message);
      return { milOn: false, dtcCount: 0, monitors: {} };
    }
  }

  // ── DTCs ───────────────────────────────────────────────────────
  async readStoredDTCs() {
    const parsed = await BluetoothService.sendCommand('03');
    return this._parseDTCLines(parsed, '43');
  }

  async readPendingDTCs() {
    const parsed = await BluetoothService.sendCommand('07');
    return this._parseDTCLines(parsed, '47');
  }

  async clearDTCs() {
    const parsed = await BluetoothService.sendCommand('04');
    if (!parsed.ok) {
      throw new Error('Clear DTCs failed: ' + (parsed.error || 'unknown'));
    }
  }

  _parseDTCLines(parsed, expectedPrefix) {
    if (!parsed.ok) return [];
    const PREFIX_MAP = {
      '0': 'P0', '1': 'P1', '2': 'P2', '3': 'P3',
      '4': 'C0', '5': 'C1', '6': 'C2', '7': 'C3',
      '8': 'B0', '9': 'B1', 'A': 'B2', 'B': 'B3',
      'C': 'U0', 'D': 'U1', 'E': 'U2', 'F': 'U3',
    };
    const dtcs = [];
    for (const line of parsed.lines) {
      let hex = line.replace(/\s+/g, '').toUpperCase();
      if (hex.startsWith(expectedPrefix)) {
        hex = hex.slice(expectedPrefix.length);
      }
      for (let i = 0; i + 4 <= hex.length; i += 4) {
        const chunk = hex.substr(i, 4);
        if (chunk === '0000') continue;
        const firstNibble = chunk[0];
        const prefix = PREFIX_MAP[firstNibble];
        if (!prefix) continue;
        const code = prefix + chunk.slice(1);
        if (code !== 'P0000' && !dtcs.includes(code)) {
          dtcs.push(code);
        }
      }
    }
    return dtcs;
  }

  // ── VIN ────────────────────────────────────────────────────────
  async readVIN() {
    try {
      const parsed = await BluetoothService.sendCommand('0902', { timeoutMs: 6000 });
      if (!parsed.ok) return null;

      let hexChars = '';
      for (const line of parsed.lines) {
        let hex = line.replace(/\s+/g, '').toUpperCase();
        if (hex.startsWith('4902')) hex = hex.slice(6); // drop "49 02 SS"
        hexChars += hex;
      }
      if (hexChars.length === 0) return null;

      let vin = '';
      for (let i = 0; i < hexChars.length && vin.length < 17; i += 2) {
        const code = parseInt(hexChars.substr(i, 2), 16);
        if (code >= 0x20 && code <= 0x7E) vin += String.fromCharCode(code);
      }
      return vin.length >= 17 ? vin.substring(0, 17) : (vin.length > 0 ? vin : null);
    } catch (e) {
      console.warn('[OBD] VIN read failed: ' + e.message);
      return null;
    }
  }

  async decodeVIN(vin) {
    if (!vin || vin.length < 17) return null;
    try {
      const url = 'https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/' +
        vin + '?format=json';
      const resp = await fetch(url);
      const data = await resp.json();
      if (!data.Results) return null;
      const get = (id) => {
        const item = data.Results.find((r) => r.VariableId === id);
        return item && item.Value && item.Value.trim() !== '' ? item.Value.trim() : null;
      };
      return {
        year: get(29) || '',
        make: get(26) || '',
        model: get(28) || '',
        engine: [get(13), get(14)].filter(Boolean).join(' ') || '',
        vin,
      };
    } catch (e) {
      console.warn('[OBD] VIN decode failed: ' + e.message);
      return null;
    }
  }

  // ── Friendly wrappers for the six "hero" metrics ───────────────
  async getRPM() { return this.readPID('0C'); }
  async getSpeed() { return this.readPID('0D'); }
  async getCoolantTemp() { return this.readPID('05'); }
  async getBatteryVoltage() { return this.readPID('42'); }

  async sendRawCommand(cmd, options) {
    return BluetoothService.sendCommand(cmd, options);
  }

  // ── Full scan ──────────────────────────────────────────────────
  async fullScan(onProgress) {
    const totalSteps = 3 + SCAN_PIDS.length;
    let step = 0;
    const report = (msg) => {
      step++;
      if (onProgress) onProgress(step, totalSteps, msg);
    };

    report('Reading monitor status...');
    const monitorStatus = await this.readMonitorStatus();

    report('Reading stored fault codes...');
    const storedDTCs = await this.readStoredDTCs();

    report('Reading pending fault codes...');
    const pendingDTCs = await this.readPendingDTCs();

    const pidReadings = {};
    for (const pid of SCAN_PIDS) {
      const def = PID_DEFS[pid];
      report('Reading ' + (def ? def.name : pid) + '...');
      const reading = await this.readPID(pid);
      if (reading) {
        pidReadings[reading.name] = {
          value: reading.value,
          unit: reading.unit,
        };
      }
    }

    const allDTCs = [...new Set([...storedDTCs, ...pendingDTCs])];
    return {
      raw_dtcs: allDTCs.map((code) => ({ code, source: 'stored' })),
      raw_pids: pidReadings,
      freeze_frame: {},
      readiness_monitors: monitorStatus.monitors,
      mil_status: monitorStatus.milOn,
      dtc_count: monitorStatus.dtcCount,
      pending_codes: pendingDTCs,
      connection_quality: 'stable',
      protocol: this._protocol || 'auto',
    };
  }
}

export default new OBDService();
