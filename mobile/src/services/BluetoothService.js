/**
 * BluetoothService — Bluetooth Classic SPP connection manager
 *
 * OBDLink MX+ exposes a Bluetooth Classic Serial Port Profile (SPP).
 * This service handles discovery, pairing, connect/disconnect, and
 * raw serial read/write over RFCOMM.
 *
 * Depends on: react-native-bluetooth-classic
 */

import RNBluetoothClassic from 'react-native-bluetooth-classic';
import {PermissionsAndroid, Platform} from 'react-native';

const OBDLINK_NAME_PATTERN = /OBDLink/i;
const CONNECT_TIMEOUT_MS = 10000;

class BluetoothService {
  constructor() {
    this._device = null;
    this._subscription = null;
  }

  get connected() {
    return this._device !== null;
  }

  get deviceName() {
    return this._device?.name || null;
  }

  get deviceAddress() {
    return this._device?.address || null;
  }

  /**
   * Request Android Bluetooth + location permissions (required for discovery).
   * Returns true if all granted.
   */
  async requestPermissions() {
    if (Platform.OS !== 'android') return true;

    const grants = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);

    return Object.values(grants).every(
      g => g === PermissionsAndroid.RESULTS.GRANTED,
    );
  }

  /**
   * Check if Bluetooth is enabled on the device.
   */
  async isBluetoothEnabled() {
    try {
      return await RNBluetoothClassic.isBluetoothEnabled();
    } catch {
      return false;
    }
  }

  /**
   * List already-paired Bluetooth devices. Filters to OBDLink if found.
   * Returns [{name, address, id}]
   */
  async getPairedDevices() {
    const devices = await RNBluetoothClassic.getBondedDevices();
    return devices.map(d => ({
      name: d.name || 'Unknown',
      address: d.address,
      id: d.id || d.address,
      isOBDLink: OBDLINK_NAME_PATTERN.test(d.name || ''),
    }));
  }

  /**
   * Start Bluetooth discovery for unpaired devices.
   * Returns a promise that resolves with discovered devices after ~12s.
   */
  async discoverDevices(onDeviceFound) {
    const discovered = [];
    try {
      const subscription = RNBluetoothClassic.onDeviceDiscovered(device => {
        const entry = {
          name: device.name || 'Unknown',
          address: device.address,
          id: device.id || device.address,
          isOBDLink: OBDLINK_NAME_PATTERN.test(device.name || ''),
        };
        discovered.push(entry);
        if (onDeviceFound) onDeviceFound(entry);
      });

      await RNBluetoothClassic.startDiscovery();

      // Discovery runs for ~12s on Android
      await new Promise(resolve => setTimeout(resolve, 12000));

      try {
        await RNBluetoothClassic.cancelDiscovery();
      } catch {
        // Already finished
      }
      subscription.remove();
    } catch (err) {
      console.warn('[BT] Discovery error:', err.message);
    }

    return discovered;
  }

  /**
   * Connect to a device by address. Establishes RFCOMM serial channel.
   */
  async connect(address) {
    if (this._device) {
      await this.disconnect();
    }

    const device = await RNBluetoothClassic.connectToDevice(address, {
      connectorType: 'rfcomm',
      delimiter: '>',
    });

    const isConnected = await device.isConnected();
    if (!isConnected) {
      throw new Error('Failed to establish RFCOMM connection');
    }

    this._device = device;
    return {
      name: device.name,
      address: device.address,
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
        await this._device.disconnect();
      } catch {
        // Already disconnected
      }
      this._device = null;
    }
  }

  /**
   * Send a raw command string to the adapter and read the response.
   * Appends \r automatically. Waits for the ELM327 '>' prompt.
   */
  async sendCommand(command) {
    if (!this._device) {
      throw new Error('Not connected to any device');
    }

    // Clear any pending data
    try {
      await this._device.clear();
    } catch {
      // Ignore clear errors
    }

    await this._device.write(command + '\r', 'ascii');

    // Read until we get the '>' prompt (ELM327 ready signal)
    const response = await this._readUntilPrompt();
    return response;
  }

  /**
   * Read serial data until the ELM327 '>' prompt appears.
   * Timeout after 5 seconds.
   */
  async _readUntilPrompt() {
    let buffer = '';
    const deadline = Date.now() + 5000;

    while (Date.now() < deadline) {
      try {
        const chunk = await this._device.read();
        if (chunk) {
          buffer += chunk;
          if (buffer.includes('>')) {
            break;
          }
        }
      } catch {
        break;
      }

      // Small delay to avoid busy loop
      await new Promise(r => setTimeout(r, 50));
    }

    // Clean up: remove echo, prompt, whitespace
    return buffer
      .replace(/>/g, '')
      .replace(/\r/g, '\n')
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .join('\n');
  }
}

export default new BluetoothService();
