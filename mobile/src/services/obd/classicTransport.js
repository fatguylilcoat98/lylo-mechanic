/*
 * LYLO Mechanic — Bluetooth Classic (RFCOMM SPP) transport
 *
 * Some OBDLink MX+ pairings come up as Bluetooth Classic devices with a
 * Serial Port Profile (SPP) socket. The old code used one-shot .read()
 * with a fixed 200ms delay, which could not reliably capture multi-frame
 * ELM327 responses. This transport uses the event-based .onDataReceived()
 * listener which stays subscribed for the entire session and forwards
 * every incoming chunk to AdapterSession's buffer.
 */

export class ClassicTransport {
  constructor(classicModule, deviceId, options = {}) {
    this._mod = classicModule;
    this._deviceId = deviceId;
    this._device = null;
    this._dataSub = null;
    this._onData = null;
    this._logger = options.logger || function () {};
  }

  get kind() { return 'classic'; }
  get profileLabel() { return 'Classic SPP'; }
  get deviceName() { return this._device ? this._device.name : null; }

  async connect(onData) {
    this._onData = onData;
    const log = this._logger;

    log('classic: connect ' + this._deviceId);
    // NOTE: we deliberately do NOT pass a delimiter option. The session
    // owns prompt detection. Letting the library buffer on '>' was a
    // subtle source of lost bytes between calls across some lib versions.
    this._device = await this._mod.connectToDevice(this._deviceId, {
      charset: 'utf-8',
    });
    log('classic: device connected: ' + (this._device.name || this._deviceId));

    // Subscribe to the device's inbound data stream for the whole session.
    // Every chunk flows to onData, which is the session buffer.
    this._dataSub = this._device.onDataReceived((event) => {
      if (event && typeof event.data === 'string' && this._onData) {
        this._onData(event.data);
      } else if (event && typeof event === 'string' && this._onData) {
        this._onData(event);
      }
    });
    log('classic: onDataReceived listener attached');
  }

  async write(data) {
    if (!this._device) throw new Error('Classic transport not connected');
    await this._device.write(data);
  }

  async disconnect() {
    const log = this._logger;
    if (this._dataSub) {
      try { this._dataSub.remove(); } catch (_) {}
      this._dataSub = null;
    }
    if (this._device) {
      try { await this._device.disconnect(); } catch (_) {}
      this._device = null;
    }
    this._onData = null;
    log('classic: disconnected');
  }
}
