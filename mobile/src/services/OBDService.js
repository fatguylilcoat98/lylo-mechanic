/**
 * OBDService — OBD-II protocol layer over ELM327
 *
 * Handles the ELM327 AT command set used by OBDLink MX+.
 * Translates raw hex responses into structured vehicle data
 * matching the backend's OBDSessionInput schema.
 *
 * Protocol flow:
 *   1. ATZ       — Reset adapter
 *   2. ATE0      — Echo off
 *   3. ATL0      — Linefeeds off
 *   4. ATS0      — Spaces off (compact hex)
 *   5. ATSP0     — Auto-detect protocol
 *   6. 0101      — Monitor status (MIL, DTC count)
 *   7. 03        — Read stored DTCs
 *   8. 07        — Read pending DTCs
 *   9. 0105      — Coolant temp
 *  10. 010C      — Engine RPM
 *  11. 010D      — Vehicle speed
 *  12. 0142      — Battery voltage
 *  13. 0106/0107 — Short/long term fuel trim
 *  14. 0101      — Readiness monitors
 */

import BluetoothService from './BluetoothService';

// OBD-II Mode 01 PID definitions: {pid, name, formula(bytes) -> value, unit}
const PID_DEFS = {
  '05': {name: 'coolant_temp', unit: 'F', parse: b => (b[0] - 40) * 9 / 5 + 32},
  '0C': {name: 'rpm', unit: 'RPM', parse: b => (b[0] * 256 + b[1]) / 4},
  '0D': {name: 'vehicle_speed', unit: 'mph', parse: b => Math.round(b[0] * 0.621371)},
  '42': {name: 'battery_voltage', unit: 'V', parse: b => (b[0] * 256 + b[1]) / 1000},
  '06': {name: 'short_fuel_trim_1', unit: '%', parse: b => (b[0] - 128) * 100 / 128},
  '07': {name: 'long_fuel_trim_1', unit: '%', parse: b => (b[0] - 128) * 100 / 128},
  '0F': {name: 'intake_air_temp', unit: 'F', parse: b => (b[0] - 40) * 9 / 5 + 32},
  '10': {name: 'maf_flow', unit: 'g/s', parse: b => (b[0] * 256 + b[1]) / 100},
  '11': {name: 'throttle_pos', unit: '%', parse: b => b[0] * 100 / 255},
};

// PIDs to read during a full scan (Mode 01)
const SCAN_PIDS = ['05', '0C', '0D', '42', '06', '07', '0F', '10', '11'];

// Readiness monitor bit positions (from Mode 01 PID 01, bytes C and D)
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
  }

  get initialized() {
    return this._initialized;
  }

  get protocol() {
    return this._protocol;
  }

  /**
   * Initialize the ELM327 adapter. Must be called after Bluetooth connect.
   * Returns adapter info string.
   */
  async initialize() {
    // Reset
    const resetResp = await BluetoothService.sendCommand('ATZ');

    // Configure for optimal OBD communication
    await BluetoothService.sendCommand('ATE0');   // Echo off
    await BluetoothService.sendCommand('ATL0');   // Linefeeds off
    await BluetoothService.sendCommand('ATS0');   // Spaces off
    await BluetoothService.sendCommand('ATH0');   // Headers off
    await BluetoothService.sendCommand('ATSP0');  // Auto protocol

    // Detect protocol with a test query
    await BluetoothService.sendCommand('0100');
    const proto = await BluetoothService.sendCommand('ATDPN');
    this._protocol = proto.trim();
    this._initialized = true;

    return {
      adapter: resetResp.trim(),
      protocol: this._protocol,
    };
  }

  /**
   * Read MIL status and DTC count from Mode 01 PID 01.
   * Returns {milOn: bool, dtcCount: number, monitors: {name: 'complete'|'incomplete'}}
   */
  async readMonitorStatus() {
    const raw = await BluetoothService.sendCommand('0101');
    const bytes = this._parseHexResponse(raw, '41', '01');

    if (!bytes || bytes.length < 4) {
      return {milOn: false, dtcCount: 0, monitors: {}};
    }

    const milOn = (bytes[0] & 0x80) !== 0;
    const dtcCount = bytes[0] & 0x7F;

    // Parse readiness monitors from bytes 2 and 3
    const monitors = {};
    const testAvail = bytes[1]; // which tests are available
    const testIncomplete = bytes[2]; // which tests are incomplete

    MONITOR_NAMES.forEach((name, i) => {
      if (i < 8) {
        const bit = 1 << i;
        if (testAvail & bit) {
          monitors[name] = (testIncomplete & bit) ? 'incomplete' : 'complete';
        }
      }
    });

    return {milOn, dtcCount, monitors};
  }

  /**
   * Read stored DTCs (Mode 03).
   * Returns array of DTC strings like ["P0420", "P0171", "C0035"]
   */
  async readStoredDTCs() {
    const raw = await BluetoothService.sendCommand('03');
    return this._parseDTCResponse(raw);
  }

  /**
   * Read pending DTCs (Mode 07).
   * Returns array of DTC strings.
   */
  async readPendingDTCs() {
    const raw = await BluetoothService.sendCommand('07');
    return this._parseDTCResponse(raw);
  }

  /**
   * Read a single PID value.
   * Returns {name, value, unit} or null if unsupported.
   */
  async readPID(pid) {
    const def = PID_DEFS[pid];
    if (!def) return null;

    try {
      const raw = await BluetoothService.sendCommand('01' + pid);
      const bytes = this._parseHexResponse(raw, '41', pid);

      if (!bytes || bytes.length === 0) return null;

      return {
        pid: pid,
        name: def.name,
        value: Math.round(def.parse(bytes) * 100) / 100,
        unit: def.unit,
      };
    } catch {
      return null;
    }
  }

  /**
   * Run a full vehicle scan. Reads all DTCs + all supported PIDs.
   * Returns data shaped for the backend's OBDSessionInput schema.
   *
   * onProgress(step, total, message) is called for each step.
   */
  async fullScan(onProgress) {
    const totalSteps = 4 + SCAN_PIDS.length; // monitor + stored + pending + PIDs
    let step = 0;

    const report = (msg) => {
      step++;
      if (onProgress) onProgress(step, totalSteps, msg);
    };

    // 1. Monitor status
    report('Reading monitor status...');
    const monitorStatus = await this.readMonitorStatus();

    // 2. Stored DTCs
    report('Reading stored fault codes...');
    const storedDTCs = await this.readStoredDTCs();

    // 3. Pending DTCs
    report('Reading pending fault codes...');
    const pendingDTCs = await this.readPendingDTCs();

    // 4. PIDs
    const pidReadings = {};
    for (const pid of SCAN_PIDS) {
      const def = PID_DEFS[pid];
      report(`Reading ${def?.name || pid}...`);

      const reading = await this.readPID(pid);
      if (reading) {
        pidReadings[reading.name] = {
          value: reading.value,
          unit: reading.unit,
        };
      }
    }

    // Build OBDSessionInput-compatible payload
    const allDTCs = [...new Set([...storedDTCs, ...pendingDTCs])];

    return {
      raw_dtcs: allDTCs.map(code => ({code, source: 'stored'})),
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

  /**
   * Clear stored DTCs and reset MIL (Mode 04).
   * WARNING: This clears all codes and resets monitors.
   */
  async clearDTCs() {
    await BluetoothService.sendCommand('04');
  }

  // ── Internal parsing ──────────────────────────────────────────

  /**
   * Parse a hex response from the ELM327.
   * Strips the mode+pid echo bytes, returns data bytes as array of ints.
   * Example: "4105BE" for Mode 01 PID 05 → [0xBE] (190 decimal)
   */
  _parseHexResponse(raw, expectedMode, expectedPid) {
    const lines = raw.split('\n').map(l => l.replace(/\s/g, '').toUpperCase());

    for (const line of lines) {
      if (line.startsWith('NODATA') || line.startsWith('ERROR') ||
          line.startsWith('UNABLE') || line.startsWith('?')) {
        return null;
      }

      const prefix = (expectedMode + expectedPid).toUpperCase();
      if (line.startsWith(prefix)) {
        const hex = line.slice(prefix.length);
        const bytes = [];
        for (let i = 0; i < hex.length; i += 2) {
          bytes.push(parseInt(hex.substr(i, 2), 16));
        }
        return bytes;
      }
    }

    return null;
  }

  /**
   * Parse a DTC response (Mode 03 or 07).
   * Each DTC is 2 bytes:
   *   Byte 1 high nibble → system prefix (P/C/B/U)
   *   Byte 1 low nibble  → first digit
   *   Byte 2             → last two digits
   */
  _parseDTCResponse(raw) {
    const lines = raw.split('\n').map(l => l.replace(/\s/g, '').toUpperCase());
    const dtcs = [];
    const PREFIX_MAP = {
      '0': 'P0', '1': 'P1', '2': 'P2', '3': 'P3',
      '4': 'C0', '5': 'C1', '6': 'C2', '7': 'C3',
      '8': 'B0', '9': 'B1', 'A': 'B2', 'B': 'B3',
      'C': 'U0', 'D': 'U1', 'E': 'U2', 'F': 'U3',
    };

    for (const line of lines) {
      if (line.startsWith('NODATA') || line.length < 4) continue;

      // Strip mode response byte if present (43 for Mode 03, 47 for Mode 07)
      let hex = line;
      if (hex.startsWith('43') || hex.startsWith('47')) {
        hex = hex.slice(2);
      }

      // Parse pairs of bytes as DTCs
      for (let i = 0; i + 3 <= hex.length; i += 4) {
        const chunk = hex.substr(i, 4);
        if (chunk === '0000') continue; // Padding

        const firstNibble = chunk[0].toUpperCase();
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
}

export default new OBDService();
