/**
 * BluetoothService — BLE connection manager for OBDLink MX+
 *
 * OBDLink MX+ exposes a BLE GATT service with a single characteristic
 * for serial data (Nordic UART Service pattern):
 *   Service UUID:  0000fff0-0000-1000-8000-00805f9b34fb
 *   TX (write):    0000fff1-0000-1000-8000-00805f9b34fb  (phone → adapter)
 *   RX (notify):   0000fff2-0000-1000-8000-00805f9b34fb  (adapter → phone)
 *
 * Some OBDLink models use the standard Nordic UART UUIDs:
 *   Service:  6e400001-b5a3-f393-e0a9-e50e24dcca9e
 *   TX:       6e400002-b5a3-f393-e0a9-e50e24dcca9e
 *   RX:       6e400003-b5a3-f393-e0a9-e50e24dcca9e
 *
 * This service tries both. Uses react-native-ble-plx (Expo compatible).
 */

import {BleManager} from 'react-native-ble-plx';
import {PermissionsAndroid, Platform} from 'react-native';

// ── Base64 polyfill ──────────────────────────────────────────────────────
// React Native's Hermes engine does NOT provide global atob/btoa.
// BLE characteristics exchange data as base64 strings, so we need these.
// This was the crash: tapping "connect" fired btoa() or atob() which
// threw ReferenceError and killed the app.
const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';

function _btoa(input) {
  let str = String(input);
  let output = '';
  for (let i = 0; i < str.length; i += 3) {
    const a = str.charCodeAt(i);
    const b = i + 1 < str.length ? str.charCodeAt(i + 1) : 0;
    const c = i + 2 < str.length ? str.charCodeAt(i + 2) : 0;
    output += chars[(a >> 2) & 63];
    output += chars[((a << 4) | (b >> 4)) & 63];
    output += i + 1 < str.length ? chars[((b << 2) | (c >> 6)) & 63] : '=';
    output += i + 2 < str.length ? chars[c & 63] : '=';
  }
  return output;
}

function _atob(input) {
  let str = String(input).replace(/=+$/, '');
  let output = '';
  for (let i = 0; i < str.length; i += 4) {
    const a = chars.indexOf(str[i]);
    const b = chars.indexOf(str[i + 1]);
    const c = chars.indexOf(str[i + 2]);
    const d = chars.indexOf(str[i + 3]);
    output += String.fromCharCode(((a << 2) | (b >> 4)) & 255);
    if (c !== -1) output += String.fromCharCode(((b << 4) | (c >> 2)) & 255);
    if (d !== -1) output += String.fromCharCode(((c << 6) | d) & 255);
  }
  return output;
}

// Known OBDLink BLE service/characteristic UUIDs
const UART_PROFILES = [
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

const OBDLINK_NAME_PATTERN = /OBDLink|OBD|ELM327|Vgate|OBDII/i;
const SCAN_TIMEOUT_MS = 10000;
const READ_TIMEOUT_MS = 5000;

class BluetoothService {
  constructor() {
    // Lazy-init BleManager — do NOT create at import time.
    // On Android 12+ creating BleManager before permissions crashes the app.
    this._manager = null;
    this._device = null;
    this._profile = null; // matched UART profile
    this._rxBuffer = '';
    this._rxResolve = null;
    this._subscription = null;
  }

  _getManager() {
    if (!this._manager) {
      try {
        this._manager = new BleManager();
      } catch (err) {
        console.warn('[BLE] Failed to create BleManager:', err.message);
        throw new Error('Bluetooth is not available on this device.');
      }
    }
    return this._manager;
  }

  get connected() {
    return this._device !== null;
  }

  get deviceName() {
    return this._device?.name || null;
  }

  get deviceId() {
    return this._device?.id || null;
  }

  /**
   * Request Android BLE permissions.
   */
  async requestPermissions() {
    if (Platform.OS !== 'android') return true;

    if (Platform.Version >= 31) {
      // Android 12+ — only need BLUETOOTH_SCAN + BLUETOOTH_CONNECT, no location
      const grants = await PermissionsAndroid.requestMultiple([
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      ]);
      return Object.values(grants).every(
        g => g === PermissionsAndroid.RESULTS.GRANTED,
      );
    }

    // Android 11 and below — BLE scanning requires location
    const grant = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    );
    return grant === PermissionsAndroid.RESULTS.GRANTED;
  }

  /**
   * Check if Bluetooth is powered on.
   */
  async isBluetoothEnabled() {
    const state = await this._getManager().state();
    if (state === 'PoweredOn') return true;

    // Wait briefly for it to power on
    return new Promise(resolve => {
      const sub = this._getManager().onStateChange(s => {
        if (s === 'PoweredOn') {
          sub.remove();
          resolve(true);
        }
      }, true);
      setTimeout(() => {
        sub.remove();
        resolve(false);
      }, 3000);
    });
  }

  /**
   * Scan for BLE devices. Calls onDeviceFound for each discovered device.
   * Returns array of all discovered devices after timeout.
   */
  async scanForDevices(onDeviceFound) {
    const discovered = new Map();

    return new Promise((resolve) => {
      this._getManager().startDeviceScan(null, {allowDuplicates: false}, (error, device) => {
        if (error) {
          console.warn('[BLE] Scan error:', error.message);
          return;
        }
        if (!device || !device.name) return;
        if (discovered.has(device.id)) return;

        const entry = {
          id: device.id,
          name: device.name,
          rssi: device.rssi,
          isOBDLink: OBDLINK_NAME_PATTERN.test(device.name),
        };
        discovered.set(device.id, entry);
        if (onDeviceFound) onDeviceFound(entry);
      });

      setTimeout(() => {
        this._getManager().stopDeviceScan();
        resolve(Array.from(discovered.values()));
      }, SCAN_TIMEOUT_MS);
    });
  }

  /**
   * Connect to a BLE device by ID. Discovers services and finds the
   * UART characteristic pair for serial OBD communication.
   */
  async connect(deviceId) {
    if (this._device) {
      try { await this.disconnect(); } catch (e) { /* ignore */ }
    }

    // Connect — wrapped in try/catch to prevent app crash
    let device;
    try {
      device = await this._getManager().connectToDevice(deviceId, {
        requestMTU: 512,
        timeout: 10000,
      });
      await device.discoverAllServicesAndCharacteristics();
    } catch (err) {
      throw new Error(`BLE connection failed: ${err.message}`);
    }

    // Find matching UART profile
    const services = await device.services();
    const serviceUUIDs = services.map(s => s.uuid.toLowerCase());

    let matched = null;
    for (const profile of UART_PROFILES) {
      if (serviceUUIDs.includes(profile.service.toLowerCase())) {
        matched = profile;
        break;
      }
    }

    if (!matched) {
      await device.cancelConnection();
      throw new Error(
        `Device "${device.name}" does not expose a known OBD UART service. ` +
        `Found services: ${serviceUUIDs.join(', ')}`,
      );
    }

    this._device = device;
    this._profile = matched;

    // Subscribe to RX notifications (adapter → phone)
    this._subscription = device.monitorCharacteristicForService(
      matched.service,
      matched.rx,
      (error, characteristic) => {
        if (error) {
          console.warn('[BLE] RX error:', error.message);
          return;
        }
        if (characteristic?.value) {
          // Value is base64 encoded
          const decoded = _atob(characteristic.value);
          this._rxBuffer += decoded;

          // If we have a pending read and the prompt arrived, resolve it
          if (this._rxResolve && this._rxBuffer.includes('>')) {
            const resolve = this._rxResolve;
            this._rxResolve = null;
            resolve(this._rxBuffer);
            this._rxBuffer = '';
          }
        }
      },
    );

    return {
      name: device.name,
      id: device.id,
      profile: matched.label,
      connected: true,
    };
  }

  /**
   * Disconnect from the current device.
   */
  async disconnect() {
    if (this._subscription) {
      this._subscription.remove();
      this._subscription = null;
    }
    if (this._device) {
      try {
        await this._device.cancelConnection();
      } catch {
        // Already disconnected
      }
      this._device = null;
      this._profile = null;
    }
    this._rxBuffer = '';
    this._rxResolve = null;
  }

  /**
   * Send a command string to the OBD adapter and wait for the response.
   * Appends \r automatically. Waits for the ELM327 '>' prompt.
   */
  async sendCommand(command) {
    if (!this._device || !this._profile) {
      throw new Error('Not connected to any device');
    }

    // Clear pending buffer
    this._rxBuffer = '';
    this._rxResolve = null;

    // Encode command + carriage return as base64
    const payload = _btoa(command + '\r');

    // Write to TX characteristic
    await this._device.writeCharacteristicWithResponseForService(
      this._profile.service,
      this._profile.tx,
      payload,
    );

    // Wait for response (until '>' prompt or timeout)
    const raw = await this._waitForPrompt();

    // Clean up response: remove echo, prompt, extra whitespace
    return raw
      .replace(/>/g, '')
      .replace(/\r/g, '\n')
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0 && line !== command)
      .join('\n');
  }

  /**
   * Wait for the ELM327 '>' prompt in the RX buffer.
   */
  _waitForPrompt() {
    // Check if it's already in the buffer
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
          // Return whatever we have even if no prompt
          const partial = this._rxBuffer;
          this._rxBuffer = '';
          if (partial.length > 0) {
            resolve(partial);
          } else {
            reject(new Error('Timeout waiting for adapter response'));
          }
        }
      }, READ_TIMEOUT_MS);
    });
  }
}

export default new BluetoothService();
