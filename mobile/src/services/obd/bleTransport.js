/*
 * LYLO Mechanic — BLE serial transport for OBDLink MX+ / STN11xx
 *
 * CRITICAL: this transport performs service discovery ONCE at connect()
 * time and then holds on to the service+characteristic references for the
 * lifetime of the session. We never re-enumerate services on every read.
 * That was the root cause of the old "can't find service" failure pattern.
 *
 * After open(), the RX characteristic is subscribed ONCE. Every inbound
 * notification feeds the onData callback supplied by AdapterSession,
 * which accumulates bytes and detects the '>' prompt to complete a
 * pending command.
 */

// ── Hermes-safe Base64 (no atob/btoa in RN Hermes) ────────────────
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';

function btoa(input) {
  const str = String(input);
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

function atob(input) {
  const str = String(input).replace(/=+$/, '');
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

// Known OBDLink / STN / ELM clone BLE serial profiles.
// We try exact matches first, then fall back to property-based autodetect.
export const BLE_UART_PROFILES = [
  {
    label: 'OBDLink FFF0',
    service: '0000fff0-0000-1000-8000-00805f9b34fb',
    tx: '0000fff1-0000-1000-8000-00805f9b34fb', // write
    rx: '0000fff2-0000-1000-8000-00805f9b34fb', // notify
  },
  {
    label: 'OBDLink FFE0',
    service: '0000ffe0-0000-1000-8000-00805f9b34fb',
    tx: '0000ffe1-0000-1000-8000-00805f9b34fb',
    rx: '0000ffe1-0000-1000-8000-00805f9b34fb', // single char write+notify
  },
  {
    label: 'Nordic UART',
    service: '6e400001-b5a3-f393-e0a9-e50e24dcca9e',
    tx: '6e400002-b5a3-f393-e0a9-e50e24dcca9e',
    rx: '6e400003-b5a3-f393-e0a9-e50e24dcca9e',
  },
];

export class BleTransport {
  constructor(bleManager, deviceId, options = {}) {
    this._mgr = bleManager;
    this._deviceId = deviceId;
    this._device = null;
    this._profile = null;
    this._sub = null;
    this._onData = null;
    this._logger = options.logger || function () {};
    this._mtu = options.mtu || 247;
  }

  get kind() { return 'ble'; }
  get profileLabel() { return this._profile ? this._profile.label : null; }
  get deviceName() { return this._device ? this._device.name : null; }

  async connect(onData) {
    this._onData = onData;
    const log = this._logger;

    log('ble: connect ' + this._deviceId);
    this._device = await this._mgr.connectToDevice(this._deviceId, {
      requestMTU: this._mtu,
      timeout: 10000,
    });
    log('ble: device connected, discovering services...');

    await this._device.discoverAllServicesAndCharacteristics();
    const services = await this._device.services();
    const uuids = services.map(function (s) { return s.uuid.toLowerCase(); });
    log('ble: services = ' + uuids.join(', '));

    // 1. Exact profile match
    let profile = null;
    for (const p of BLE_UART_PROFILES) {
      if (uuids.indexOf(p.service.toLowerCase()) !== -1) {
        profile = p;
        break;
      }
    }

    // 2. Autodetect: any service with a writeable + notifiable char pair
    if (!profile) {
      log('ble: no known profile, auto-detecting...');
      for (const s of services) {
        const chars = await s.characteristics();
        const writeChar = chars.find(function (c) {
          return c.isWritableWithResponse || c.isWritableWithoutResponse;
        });
        const notifyChar = chars.find(function (c) {
          return c.isNotifiable || c.isIndicatable;
        });
        if (writeChar && notifyChar) {
          profile = {
            label: 'Auto ' + s.uuid.slice(0, 8),
            service: s.uuid,
            tx: writeChar.uuid,
            rx: notifyChar.uuid,
          };
          log('ble: autodetected ' + profile.label +
              ' tx=' + profile.tx + ' rx=' + profile.rx);
          break;
        }
      }
    }

    if (!profile) {
      const err = new Error(
        'Connected but no OBD serial channel found on this device. ' +
        'Services: ' + uuids.join(', ')
      );
      try { await this._device.cancelConnection(); } catch (_) {}
      this._device = null;
      throw err;
    }

    this._profile = profile;
    log('ble: locked profile ' + profile.label +
        ' svc=' + profile.service);

    // Subscribe to RX once. This subscription lives for the whole session.
    // We never re-subscribe or re-discover between commands.
    this._sub = this._device.monitorCharacteristicForService(
      profile.service,
      profile.rx,
      (error, characteristic) => {
        if (error) {
          log('ble: rx monitor error: ' + (error.message || error));
          return;
        }
        if (characteristic && characteristic.value) {
          const decoded = atob(characteristic.value);
          if (this._onData) this._onData(decoded);
        }
      }
    );
    log('ble: subscribed to RX notifications on ' + profile.rx);
  }

  async write(data) {
    if (!this._device || !this._profile) {
      throw new Error('BLE transport not connected');
    }
    const log = this._logger;
    // 20-byte BLE default ATT payload is the safe chunk size. Even at
    // higher MTU, ELM text commands fit in one or two chunks easily.
    const CHUNK = 20;
    for (let i = 0; i < data.length; i += CHUNK) {
      const chunk = data.slice(i, i + CHUNK);
      const b64 = btoa(chunk);
      try {
        await this._device.writeCharacteristicWithResponseForService(
          this._profile.service,
          this._profile.tx,
          b64
        );
      } catch (e) {
        log('ble: writeWithResponse failed (' + (e.message || e) +
            '), falling back to writeWithoutResponse');
        await this._device.writeCharacteristicWithoutResponseForService(
          this._profile.service,
          this._profile.tx,
          b64
        );
      }
    }
  }

  async disconnect() {
    const log = this._logger;
    if (this._sub) {
      try { this._sub.remove(); } catch (_) {}
      this._sub = null;
    }
    if (this._device) {
      try { await this._device.cancelConnection(); } catch (_) {}
      this._device = null;
    }
    this._profile = null;
    this._onData = null;
    log('ble: disconnected');
  }
}
