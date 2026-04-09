/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Truth · Safety · We Got Your Back
 *
 * BluetoothService — thin facade over AdapterSession.
 *
 * Responsibilities:
 *   1. Permissions + BT-enabled checks
 *   2. Device scanning (Classic bonded + Classic discovery + BLE scan)
 *   3. Session factory: given a device, build a BleTransport or
 *      ClassicTransport, wrap it in an AdapterSession, and open it.
 *
 * This file does NOT implement any request/response logic. All of the
 * command/queue/parsing behavior lives in obd/session.js. That split is
 * what makes the new architecture stable: scanning and connecting are
 * one-shot operations, while command flow is owned by a persistent
 * session object that never re-discovers services after connect.
 */

import { PermissionsAndroid, Platform } from 'react-native';
import { AdapterSession, setLogger } from './obd/session';
import { BleTransport } from './obd/bleTransport';
import { ClassicTransport } from './obd/classicTransport';

// ── Lazy native module loading ────────────────────────────────────
// Loading these modules before runtime permissions are granted can
// crash the native side. Lazy-load + catch so the app can still render
// the scan screen even if a module is missing.

let _RNBluetoothClassic = null;
let _BleManagerCtor = null;

function getClassicModule() {
  if (_RNBluetoothClassic === null) {
    try {
      const mod = require('react-native-bluetooth-classic');
      _RNBluetoothClassic = mod.default || mod;
      log('Classic module loaded');
    } catch (e) {
      log('Classic module unavailable: ' + (e.message || e));
      _RNBluetoothClassic = false;
    }
  }
  return _RNBluetoothClassic || null;
}

function getBleManagerCtor() {
  if (_BleManagerCtor === null) {
    try {
      _BleManagerCtor = require('react-native-ble-plx').BleManager;
      log('BLE module loaded');
    } catch (e) {
      log('BLE module unavailable: ' + (e.message || e));
      _BleManagerCtor = false;
    }
  }
  return _BleManagerCtor || null;
}

// ── Log sink ───────────────────────────────────────────────────────
const _log = [];
function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  const line = '[' + ts + '] ' + msg;
  _log.push(line);
  if (_log.length > 500) _log.shift();
  console.log('[BT] ' + msg);
}

// Route AdapterSession's internal logs through the same ring buffer
setLogger(function (m) { log(m); });

// ── Constants ──────────────────────────────────────────────────────
const OBDLINK_NAME_PATTERN = /OBDLink|OBD|ELM327|Vgate|OBDII/i;
const CLASSIC_DISCOVERY_MS = 15000;
const BLE_SCAN_MS = 12000;

// ══════════════════════════════════════════════════════════════════
// BluetoothService
// ══════════════════════════════════════════════════════════════════
class BluetoothService {
  constructor() {
    this._bleManager = null;
    this._session = null;     // current AdapterSession (or null)
  }

  get connected() { return this._session !== null && this._session.ready; }
  get session() { return this._session; }
  get mode() { return this._session ? this._session.transportKind : null; }
  get deviceName() { return this._session ? this._session.deviceName : null; }
  get debugLog() { return _log.slice(); }

  // ── Permissions ──────────────────────────────────────────────────
  async requestPermissions() {
    if (Platform.OS !== 'android') return true;

    const perms = [];
    if (Platform.Version >= 31) {
      perms.push(
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      );
    }
    // Classic discovery always needs location on Android
    perms.push(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);

    log('Requesting ' + perms.length + ' permissions (API ' + Platform.Version + ')');
    const grants = await PermissionsAndroid.requestMultiple(perms);

    for (const [perm, result] of Object.entries(grants)) {
      log('  ' + perm.split('.').pop() + ': ' + result);
    }

    const allGranted = Object.values(grants).every(
      g => g === PermissionsAndroid.RESULTS.GRANTED
    );
    log(allGranted ? 'All permissions granted' : 'Some permissions denied');
    return allGranted;
  }

  // ── BT enabled check ────────────────────────────────────────────
  async isBluetoothEnabled() {
    const classic = getClassicModule();
    if (classic) {
      try {
        const enabled = await classic.isBluetoothEnabled();
        log('Classic BT enabled: ' + enabled);
        return enabled;
      } catch (e) {
        log('Classic BT check failed: ' + (e.message || e));
      }
    }
    const BleManagerCtor = getBleManagerCtor();
    if (BleManagerCtor) {
      try {
        if (!this._bleManager) this._bleManager = new BleManagerCtor();
        const state = await this._bleManager.state();
        log('BLE state: ' + state);
        if (state === 'PoweredOn') return true;
        return new Promise((resolve) => {
          const sub = this._bleManager.onStateChange((s) => {
            if (s === 'PoweredOn') { sub.remove(); resolve(true); }
          }, true);
          setTimeout(() => { sub.remove(); resolve(false); }, 3000);
        });
      } catch (e) {
        log('BLE state check failed: ' + (e.message || e));
      }
    }
    log('No Bluetooth module available');
    return false;
  }

  // ══════════════════════════════════════════════════════════════════
  // SCANNING
  // ══════════════════════════════════════════════════════════════════
  async scanForDevices(onDeviceFound) {
    const all = new Map();
    const emit = (d) => {
      if (all.has(d.id)) return;
      all.set(d.id, d);
      if (onDeviceFound) onDeviceFound(d);
    };
    await this._scanClassicBonded(emit);
    await this._scanClassicDiscovery(emit);
    await this._scanBle(emit);
    log('Scan complete: ' + all.size + ' devices');
    return Array.from(all.values());
  }

  async _scanClassicBonded(emit) {
    const classic = getClassicModule();
    if (!classic) return;
    try {
      log('Checking bonded Classic devices...');
      const bonded = await classic.getBondedDevices();
      log('Found ' + bonded.length + ' bonded devices');
      for (const d of bonded) {
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
      log('Bonded scan error: ' + (e.message || e));
    }
  }

  async _scanClassicDiscovery(emit) {
    const classic = getClassicModule();
    if (!classic) return;
    try {
      log('Starting Classic discovery (' + (CLASSIC_DISCOVERY_MS / 1000) + 's)...');
      const discovered = await classic.startDiscovery();
      log('Classic discovery returned ' + discovered.length + ' devices');
      for (const d of discovered) {
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
      log('Classic discovery error: ' + (e.message || e));
      try { await classic.cancelDiscovery(); } catch (_) {}
    }
  }

  async _scanBle(emit) {
    const BleManagerCtor = getBleManagerCtor();
    if (!BleManagerCtor) return;
    try {
      if (!this._bleManager) this._bleManager = new BleManagerCtor();
      log('Starting BLE scan (' + (BLE_SCAN_MS / 1000) + 's)...');
      await new Promise((resolve) => {
        this._bleManager.startDeviceScan(null, { allowDuplicates: false }, (error, device) => {
          if (error) {
            log('BLE scan error: ' + (error.message || error));
            return;
          }
          if (!device || !device.name) return;
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
          try { this._bleManager.stopDeviceScan(); } catch (_) {}
          log('BLE scan stopped');
          resolve();
        }, BLE_SCAN_MS);
      });
    } catch (e) {
      log('BLE scan error: ' + (e.message || e));
    }
  }

  // ══════════════════════════════════════════════════════════════════
  // CONNECTION — builds a session and opens it
  // ══════════════════════════════════════════════════════════════════
  async connect(deviceId, deviceType) {
    // Tear down any prior session first
    if (this._session) {
      try { await this._session.close(); } catch (_) {}
      this._session = null;
    }

    if (!deviceType) {
      // Heuristic: MAC-style id implies Classic; UUID-style implies BLE
      deviceType = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(deviceId)
        ? 'classic' : 'ble';
      log('Auto-detected deviceType=' + deviceType + ' for ' + deviceId);
    }

    let transport;
    if (deviceType === 'classic') {
      const classic = getClassicModule();
      if (!classic) throw new Error('Bluetooth Classic module unavailable');
      transport = new ClassicTransport(classic, deviceId, {
        logger: (m) => log(m),
      });
    } else {
      const BleManagerCtor = getBleManagerCtor();
      if (!BleManagerCtor) throw new Error('BLE module unavailable');
      if (!this._bleManager) this._bleManager = new BleManagerCtor();
      transport = new BleTransport(this._bleManager, deviceId, {
        logger: (m) => log(m),
      });
    }

    const session = new AdapterSession(transport);
    await session.open();
    this._session = session;

    return {
      name: session.deviceName || deviceId,
      id: deviceId,
      profile: session.profileLabel,
      connected: true,
    };
  }

  // ── Forward sendCommand to the active session ──────────────────
  // Returns the structured parsed response: { ok, lines, error, ... }
  async sendCommand(command, options) {
    if (!this._session) throw new Error('Not connected to any device');
    return this._session.sendCommand(command, options);
  }

  async initializeSession() {
    if (!this._session) throw new Error('Not connected to any device');
    return this._session.initialize();
  }

  async disconnect() {
    log('Disconnecting...');
    if (this._session) {
      try { await this._session.close(); } catch (_) {}
      this._session = null;
    }
    log('Disconnected');
  }
}

export default new BluetoothService();
