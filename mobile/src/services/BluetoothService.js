/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 *
 * BluetoothService — Dual-mode: Classic (SPP) + BLE
 *
 * OBDLink MX+ supports both Bluetooth Classic and BLE.
 * This service tries Classic first (bonded devices + discovery),
 * then falls back to BLE scanning.
 *
 * Classic uses RFCOMM serial (react-native-bluetooth-classic).
 * BLE uses Nordic UART (react-native-ble-plx).
 */

import {PermissionsAndroid, Platform} from 'react-native';

// ── Lazy imports ────────────────────────────────────────────────
// Both native modules can crash if loaded before permissions are granted
// or if the module isn't linked. We import lazily and catch failures.

let RNBluetoothClassic = null;
let BleManager = null;

function _getClassicModule() {
  if (RNBluetoothClassic === null) {
    try {
      const mod = require('react-native-bluetooth-classic');
      RNBluetoothClassic = mod.default || mod;
      console.log('[BT] Classic module loaded');
    } catch (e) {
      console.warn('[BT] Classic module not available:', e.message);
      RNBluetoothClassic = false; // mark as failed so we don't retry
    }
  }
  return RNBluetoothClassic || null;
}

function _getBleModule() {
  if (BleManager === null) {
    try {
      BleManager = require('react-native-ble-plx').BleManager;
      console.log('[BT] BLE module loaded');
    } catch (e) {
      console.warn('[BT] BLE module not available:', e.message);
      BleManager = false;
    }
  }
  return BleManager || null;
}

// ── Base64 polyfill ────────────────────────────────────────────
// Hermes doesn't have atob/btoa — needed for BLE characteristic encoding
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';

function _btoa(input) {
  let str = String(input);
  let out = '';
  for (let i = 0; i < str.length; i += 3) {
    const a = str.charCodeAt(i);
    const b = i + 1 < str.length ? str.charCodeAt(i + 1) : 0;
    const c = i + 2 < str.length ? str.charCodeAt(i + 2) : 0;
    out += B64[(a >> 2) & 63];
    out += B64[((a << 4) | (b >> 4)) & 63];
    out += i + 1 < str.length ? B64[((b << 2) | (c >> 6)) & 63] : '=';
    out += i + 2 < str.length ? B64[c & 63] : '=';
  }
  return out;
}

function _atob(input) {
  let str = String(input).replace(/=+$/, '');
  let out = '';
  for (let i = 0; i < str.length; i += 4) {
    const a = B64.indexOf(str[i]);
    const b = B64.indexOf(str[i + 1]);
    const c = B64.indexOf(str[i + 2]);
    const d = B64.indexOf(str[i + 3]);
    out += String.fromCharCode(((a << 2) | (b >> 4)) & 255);
    if (c !== -1) out += String.fromCharCode(((b << 4) | (c >> 2)) & 255);
    if (d !== -1) out += String.fromCharCode(((c << 6) | d) & 255);
  }
  return out;
}

// ── Constants ──────────────────────────────────────────────────

const OBDLINK_NAME_PATTERN = /OBDLink|OBD|ELM327|Vgate|OBDII/i;

// BLE UART profiles for OBDLink
const BLE_UART_PROFILES = [
  {
    label: 'OBDLink FFF0',
    service: '0000fff0-0000-1000-8000-00805f9b34fb',
    tx: '0000fff1-0000-1000-8000-00805f9b34fb',
    rx: '0000fff2-0000-1000-8000-00805f9b34fb',
  },
  {
    label: 'Nordic UART',
    service: '6e400001-b5a3-f393-e0a9-e50e24dcca9e',
    tx: '6e400002-b5a3-f393-e0a9-e50e24dcca9e',
    rx: '6e400003-b5a3-f393-e0a9-e50e24dcca9e',
  },
];

const CLASSIC_SCAN_MS = 30000;   // 30 seconds for Classic discovery
const BLE_SCAN_MS = 15000;       // 15 seconds for BLE scan
const READ_TIMEOUT_MS = 5000;

// ── Log helper ─────────────────────────────────────────────────
const _log = [];
function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  const entry = `[${ts}] ${msg}`;
  _log.push(entry);
  console.log('[BT]', msg);
}

// ════════════════════════════════════════════════════════════════
// BluetoothService
// ════════════════════════════════════════════════════════════════

class BluetoothService {
  constructor() {
    this._mode = null;          // 'classic' | 'ble' | null
    this._classicDevice = null; // Connected Classic device
    this._bleManager = null;    // BleManager instance
    this._bleDevice = null;     // Connected BLE device
    this._bleProfile = null;    // Matched UART profile
    this._rxBuffer = '';
    this._rxResolve = null;
    this._subscription = null;
  }

  get connected() {
    return this._classicDevice !== null || this._bleDevice !== null;
  }

  get deviceName() {
    if (this._classicDevice) return this._classicDevice.name;
    if (this._bleDevice) return this._bleDevice.name;
    return null;
  }

  get mode() {
    return this._mode;
  }

  get debugLog() {
    return [..._log];
  }

  // ── Permissions ──────────────────────────────────────────────

  async requestPermissions() {
    if (Platform.OS !== 'android') return true;

    const perms = [];

    if (Platform.Version >= 31) {
      perms.push(
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      );
    }

    // Classic Bluetooth discovery ALWAYS needs location on Android
    perms.push(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);

    log(`Requesting ${perms.length} permissions (API ${Platform.Version})`);

    const grants = await PermissionsAndroid.requestMultiple(perms);

    for (const [perm, result] of Object.entries(grants)) {
      const short = perm.split('.').pop();
      log(`  ${short}: ${result}`);
    }

    const allGranted = Object.values(grants).every(
      g => g === PermissionsAndroid.RESULTS.GRANTED,
    );

    log(allGranted ? 'All permissions granted' : 'Some permissions denied');
    return allGranted;
  }

  // ── Bluetooth enabled check ──────────────────────────────────

  async isBluetoothEnabled() {
    // Try Classic check first
    const classic = _getClassicModule();
    if (classic) {
      try {
        const enabled = await classic.isBluetoothEnabled();
        log(`Classic BT enabled: ${enabled}`);
        return enabled;
      } catch (e) {
        log(`Classic BT check failed: ${e.message}`);
      }
    }

    // Fall back to BLE check
    const BleManagerClass = _getBleModule();
    if (BleManagerClass) {
      try {
        if (!this._bleManager) this._bleManager = new BleManagerClass();
        const state = await this._bleManager.state();
        const enabled = state === 'PoweredOn';
        log(`BLE state: ${state}`);
        if (!enabled) {
          // Wait up to 3s for it to power on
          return new Promise(resolve => {
            const sub = this._bleManager.onStateChange(s => {
              if (s === 'PoweredOn') { sub.remove(); resolve(true); }
            }, true);
            setTimeout(() => { sub.remove(); resolve(false); }, 3000);
          });
        }
        return enabled;
      } catch (e) {
        log(`BLE state check failed: ${e.message}`);
      }
    }

    log('No Bluetooth module available');
    return false;
  }

  // ════════════════════════════════════════════════════════════
  // SCANNING — finds all devices, Classic + BLE
  // ════════════════════════════════════════════════════════════

  async scanForDevices(onDeviceFound) {
    const allDevices = new Map();

    const emit = (device) => {
      if (allDevices.has(device.id)) return;
      allDevices.set(device.id, device);
      if (onDeviceFound) onDeviceFound(device);
    };

    // ── Phase 1: Classic bonded (paired) devices ──
    await this._scanClassicBonded(emit);

    // ── Phase 2: Classic discovery (finds new devices) ──
    await this._scanClassicDiscovery(emit);

    // ── Phase 3: BLE scan (fallback) ──
    await this._scanBLE(emit);

    log(`Scan complete: ${allDevices.size} total devices found`);
    return Array.from(allDevices.values());
  }

  async _scanClassicBonded(emit) {
    const classic = _getClassicModule();
    if (!classic) {
      log('Classic module not available — skipping bonded scan');
      return;
    }

    try {
      log('Checking bonded (paired) Classic devices...');
      const bonded = await classic.getBondedDevices();
      log(`Found ${bonded.length} bonded devices`);

      for (const d of bonded) {
        log(`  Bonded: "${d.name || 'unnamed'}" [${d.address || d.id}]`);
        emit({
          id: d.address || d.id,
          name: d.name || 'Unknown Device',
          rssi: null,
          isOBDLink: OBDLINK_NAME_PATTERN.test(d.name || ''),
          type: 'classic',
          bonded: true,
        });
      }
    } catch (e) {
      log(`Bonded scan error: ${e.message}`);
    }
  }

  async _scanClassicDiscovery(emit) {
    const classic = _getClassicModule();
    if (!classic) return;

    try {
      log(`Starting Classic discovery (${CLASSIC_SCAN_MS / 1000}s)...`);
      const discovered = await classic.startDiscovery();
      log(`Classic discovery returned ${discovered.length} devices`);

      for (const d of discovered) {
        log(`  Discovered: "${d.name || 'unnamed'}" [${d.address || d.id}]`);
        emit({
          id: d.address || d.id,
          name: d.name || 'Unknown Device',
          rssi: null,
          isOBDLink: OBDLINK_NAME_PATTERN.test(d.name || ''),
          type: 'classic',
          bonded: false,
        });
      }
    } catch (e) {
      log(`Classic discovery error: ${e.message}`);
      // Try to cancel any in-progress discovery
      try { await classic.cancelDiscovery(); } catch (_) {}
    }
  }

  async _scanBLE(emit) {
    const BleManagerClass = _getBleModule();
    if (!BleManagerClass) {
      log('BLE module not available — skipping BLE scan');
      return;
    }

    try {
      if (!this._bleManager) this._bleManager = new BleManagerClass();
      log(`Starting BLE scan (${BLE_SCAN_MS / 1000}s)...`);

      await new Promise((resolve) => {
        this._bleManager.startDeviceScan(null, {allowDuplicates: false}, (error, device) => {
          if (error) {
            log(`BLE scan error: ${error.message}`);
            return;
          }
          if (!device || !device.name) return;

          log(`  BLE found: "${device.name}" [${device.id}] RSSI:${device.rssi}`);
          emit({
            id: device.id,
            name: device.name,
            rssi: device.rssi,
            isOBDLink: OBDLINK_NAME_PATTERN.test(device.name),
            type: 'ble',
            bonded: false,
          });
        });

        setTimeout(() => {
          this._bleManager.stopDeviceScan();
          log('BLE scan stopped');
          resolve();
        }, BLE_SCAN_MS);
      });
    } catch (e) {
      log(`BLE scan error: ${e.message}`);
    }
  }

  // ════════════════════════════════════════════════════════════
  // CONNECTION
  // ════════════════════════════════════════════════════════════

  async connect(deviceId, deviceType) {
    if (this.connected) {
      try { await this.disconnect(); } catch (e) { /* ignore */ }
    }

    // Auto-detect type if not specified
    if (!deviceType) {
      // If it looks like a MAC address (AA:BB:CC:DD:EE:FF), it's Classic
      deviceType = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(deviceId) ? 'classic' : 'ble';
      log(`Auto-detected device type: ${deviceType} for ${deviceId}`);
    }

    if (deviceType === 'classic') {
      return this._connectClassic(deviceId);
    } else {
      return this._connectBLE(deviceId);
    }
  }

  async _connectClassic(deviceId) {
    const classic = _getClassicModule();
    if (!classic) throw new Error('Bluetooth Classic not available');

    log(`Connecting Classic to ${deviceId}...`);

    try {
      const device = await classic.connectToDevice(deviceId, {
        delimiter: '>',
        charset: 'utf-8',
      });

      this._classicDevice = device;
      this._mode = 'classic';
      log(`Classic connected: ${device.name || deviceId}`);

      return {
        name: device.name || deviceId,
        id: deviceId,
        profile: 'Classic SPP',
        connected: true,
      };
    } catch (e) {
      log(`Classic connection failed: ${e.message}`);
      throw new Error(`Classic connection failed: ${e.message}`);
    }
  }

  async _connectBLE(deviceId) {
    const BleManagerClass = _getBleModule();
    if (!BleManagerClass) throw new Error('BLE not available');

    if (!this._bleManager) this._bleManager = new BleManagerClass();
    log(`Connecting BLE to ${deviceId}...`);

    let device;
    try {
      device = await this._bleManager.connectToDevice(deviceId, {
        requestMTU: 512,
        timeout: 10000,
      });
      await device.discoverAllServicesAndCharacteristics();
    } catch (err) {
      throw new Error(`BLE connection failed: ${err.message}`);
    }

    // Find UART profile
    const services = await device.services();
    const serviceUUIDs = services.map(s => s.uuid.toLowerCase());
    log(`BLE services: ${serviceUUIDs.join(', ')}`);

    let matched = null;
    for (const profile of BLE_UART_PROFILES) {
      if (serviceUUIDs.includes(profile.service.toLowerCase())) {
        matched = profile;
        break;
      }
    }

    if (!matched) {
      await device.cancelConnection();
      throw new Error(
        `Device does not expose a known OBD UART service. Services: ${serviceUUIDs.join(', ')}`,
      );
    }

    this._bleDevice = device;
    this._bleProfile = matched;
    this._mode = 'ble';

    // Subscribe to RX
    this._subscription = device.monitorCharacteristicForService(
      matched.service, matched.rx,
      (error, characteristic) => {
        if (error) { log(`BLE RX error: ${error.message}`); return; }
        if (characteristic?.value) {
          const decoded = _atob(characteristic.value);
          this._rxBuffer += decoded;
          if (this._rxResolve && this._rxBuffer.includes('>')) {
            const resolve = this._rxResolve;
            this._rxResolve = null;
            resolve(this._rxBuffer);
            this._rxBuffer = '';
          }
        }
      },
    );

    log(`BLE connected via ${matched.label}`);
    return {
      name: device.name,
      id: device.id,
      profile: matched.label,
      connected: true,
    };
  }

  // ════════════════════════════════════════════════════════════
  // SEND COMMAND
  // ════════════════════════════════════════════════════════════

  async sendCommand(command) {
    if (this._mode === 'classic') {
      return this._sendClassic(command);
    } else if (this._mode === 'ble') {
      return this._sendBLE(command);
    } else {
      throw new Error('Not connected to any device');
    }
  }

  async _sendClassic(command) {
    if (!this._classicDevice) throw new Error('Classic device not connected');

    try {
      await this._classicDevice.write(command + '\r');

      // Wait for response with > prompt
      await new Promise(r => setTimeout(r, 200));
      const response = await this._classicDevice.read();

      if (!response) return '';

      // Clean up: remove echo and prompt
      return response
        .replace(/>/g, '')
        .replace(/\r/g, '\n')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0 && line !== command)
        .join('\n');
    } catch (e) {
      throw new Error(`Classic command failed: ${e.message}`);
    }
  }

  async _sendBLE(command) {
    if (!this._bleDevice || !this._bleProfile) throw new Error('BLE device not connected');

    this._rxBuffer = '';
    this._rxResolve = null;

    const payload = _btoa(command + '\r');

    await this._bleDevice.writeCharacteristicWithResponseForService(
      this._bleProfile.service,
      this._bleProfile.tx,
      payload,
    );

    const raw = await this._waitForPrompt();

    return raw
      .replace(/>/g, '')
      .replace(/\r/g, '\n')
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0 && line !== command)
      .join('\n');
  }

  _waitForPrompt() {
    if (this._rxBuffer.includes('>')) {
      const result = this._rxBuffer;
      this._rxBuffer = '';
      return Promise.resolve(result);
    }

    return new Promise((resolve, reject) => {
      this._rxResolve = resolve;
      setTimeout(() => {
        if (this._rxResolve === resolve) {
          this._rxResolve = null;
          const partial = this._rxBuffer;
          this._rxBuffer = '';
          if (partial.length > 0) resolve(partial);
          else reject(new Error('Timeout waiting for adapter response'));
        }
      }, READ_TIMEOUT_MS);
    });
  }

  // ════════════════════════════════════════════════════════════
  // DISCONNECT
  // ════════════════════════════════════════════════════════════

  async disconnect() {
    log('Disconnecting...');

    if (this._subscription) {
      this._subscription.remove();
      this._subscription = null;
    }

    if (this._classicDevice) {
      try { await this._classicDevice.disconnect(); } catch (_) {}
      this._classicDevice = null;
    }

    if (this._bleDevice) {
      try { await this._bleDevice.cancelConnection(); } catch (_) {}
      this._bleDevice = null;
      this._bleProfile = null;
    }

    this._mode = null;
    this._rxBuffer = '';
    this._rxResolve = null;
    log('Disconnected');
  }
}

export default new BluetoothService();
