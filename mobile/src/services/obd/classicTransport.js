/*
 * LYLO Mechanic — Bluetooth Classic (RFCOMM SPP) transport
 *
 * Some OBDLink MX+ pairings come up as Bluetooth Classic devices with a
 * Serial Port Profile (SPP) socket. This transport uses the event-based
 * .onDataReceived() listener which stays subscribed for the entire
 * session and forwards every incoming chunk to AdapterSession's buffer.
 *
 * Why delimiter: '>' matters
 * ──────────────────────────
 * react-native-bluetooth-classic's default connector is a "delimited
 * string" reader. On construction it takes a delimiter byte and the
 * native side keeps reading from the RFCOMM socket into an internal
 * buffer, only emitting an onDataReceived event when it sees that
 * delimiter.
 *
 * If no delimiter is specified, the library defaults to '\n'. But
 * ELM327 / STN11xx responses end with '\r' followed by the '>' prompt
 * and NEVER contain a '\n'. With the default delimiter the native
 * buffer grows forever and onDataReceived never fires — which is
 * exactly what we observed: ATZ writes, adapter replies, 5 seconds
 * pass, session times out with zero received bytes.
 *
 * Fix: use '>' as the delimiter. The ELM '>' prompt is the unambiguous
 * end-of-response marker for every AT and OBD command. Every time the
 * adapter finishes a response, the library emits exactly one event and
 * we forward it to the session. If the library strips the '>' before
 * emitting (behavior varies by version), we re-append it so the
 * session's prompt detector still fires.
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

    // Try the property name variants used across library versions.
    // v1.73-rc accepts lowercase keys; older releases used UPPER_SNAKE.
    // Passing both forms is harmless if the lib ignores the ones it
    // doesn't know.
    this._device = await this._mod.connectToDevice(this._deviceId, {
      delimiter: '>',
      charset: 'utf-8',
      DELIMITER: '>',
      DEVICE_CHARSET: 'utf-8',
      CONNECTOR_TYPE: 'rfcomm',
      READ_SIZE: 1024,
    });
    log('classic: device connected: ' + (this._device.name || this._deviceId));

    // Subscribe to the device's inbound data stream for the whole session.
    // Each event corresponds to one delimiter-terminated chunk, which for
    // ELM means one complete command response.
    this._dataSub = this._device.onDataReceived((event) => {
      // Handle both event shapes seen across library versions.
      let data = null;
      if (event == null) {
        log('classic: rx event null');
        return;
      }
      if (typeof event === 'string') {
        data = event;
      } else if (typeof event.data === 'string') {
        data = event.data;
      } else {
        log('classic: rx event unknown shape: ' +
            JSON.stringify(event).slice(0, 80));
        return;
      }

      // Log the raw received chunk so the in-app debug log shows
      // conclusively whether bytes are arriving. Truncate long lines.
      const preview = data.replace(/\r/g, '\\r').replace(/\n/g, '\\n');
      log('classic: rx "' + preview.slice(0, 120) +
          (preview.length > 120 ? '...' : '') +
          '" (' + data.length + 'b)');

      // Re-add the prompt character if the lib stripped it when splitting
      // on the delimiter. The session's _handleData looks for '>' to
      // complete a pending command.
      if (data.indexOf('>') === -1) data = data + '>';

      if (this._onData) this._onData(data);
    });
    log('classic: onDataReceived listener attached (delimiter=">")');
  }

  async write(data) {
    if (!this._device) throw new Error('Classic transport not connected');
    const log = this._logger;
    // Drop any leftover bytes in the native delimited buffer before
    // sending a new command. Without this, a delayed response from a
    // previous (possibly timed-out) command could be falsely attributed
    // to the next command.
    try {
      await this._device.clear();
    } catch (e) {
      log('classic: clear() failed (non-fatal): ' + (e.message || e));
    }
    const preview = data.replace(/\r/g, '\\r').replace(/\n/g, '\\n');
    log('classic: tx "' + preview + '" (' + data.length + 'b)');
    await this._device.write(data);
    log('classic: tx done');
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
