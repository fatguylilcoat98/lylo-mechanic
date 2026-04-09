/*
 * LYLO Mechanic — AdapterSession
 *
 * A persistent command/response session over either BLE or Classic
 * Bluetooth. This is the object that models an OBDLink adapter as what
 * it actually is: a serial command interface, not a generic BLE GATT
 * device.
 *
 * Lifecycle:
 *
 *   const session = new AdapterSession(transport);
 *   await session.open();          // connect + discover + subscribe ONCE
 *   await session.initialize();    // ATZ, ATE0, ATL0, ATS0, ATH0, ATSP0
 *   const parsed = await session.sendCommand('010C');
 *   ...
 *   await session.close();
 *
 * Guarantees:
 *   - Service discovery happens exactly once, at open() time.
 *   - The RX subscription is set up exactly once, at open() time.
 *   - Commands are serialized through an internal queue, so two
 *     callers can never stomp on each other's response bytes.
 *   - Every command has a timeout that cannot hang forever.
 *   - If a command times out or errors, the buffer is cleared before
 *     the next command so there's no cross-contamination.
 *   - sendCommand() returns a structured { ok, lines, error, ... }
 *     object, never raw ELM text.
 */

import { parseResponse } from './parser';

// Sensible defaults. Individual commands can override via options.
const DEFAULT_TIMEOUT_MS = 4000;
const RESET_TIMEOUT_MS = 5000;     // ATZ is slow
const SEARCH_TIMEOUT_MS = 10000;   // 0100 while searching protocol

export const SESSION_STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  READY: 'ready',
  QUERYING: 'querying',
  CLOSING: 'closing',
  CLOSED: 'closed',
  ERROR: 'error',
};

// Default init sequence. Order matters.
// ATZ  — reset adapter
// ATE0 — echo off (stop seeing our own commands back)
// ATL0 — linefeeds off
// ATS0 — spaces off (compact hex)
// ATH0 — headers off
// ATSP0 — auto-select OBD protocol
export const DEFAULT_INIT_SEQUENCE = [
  { cmd: 'ATZ',  timeoutMs: RESET_TIMEOUT_MS, tolerateError: true },
  { cmd: 'ATE0', timeoutMs: DEFAULT_TIMEOUT_MS },
  { cmd: 'ATL0', timeoutMs: DEFAULT_TIMEOUT_MS },
  { cmd: 'ATS0', timeoutMs: DEFAULT_TIMEOUT_MS },
  { cmd: 'ATH0', timeoutMs: DEFAULT_TIMEOUT_MS },
  { cmd: 'ATSP0', timeoutMs: DEFAULT_TIMEOUT_MS },
];

let _loggerSink = (line) => { console.log('[OBD] ' + line); };
export function setLogger(fn) { _loggerSink = fn; }

function log(msg) { try { _loggerSink(msg); } catch (_) {} }

export class AdapterSession {
  constructor(transport, options = {}) {
    this._transport = transport;
    this._state = SESSION_STATE.IDLE;
    this._buffer = '';
    this._queue = [];
    this._running = false;
    this._pending = null;   // { command, timer, resolve, reject, timeoutMs }
    this._listeners = new Set();
    this._protocol = null;
    this._adapterId = null;
    this._lastActivity = 0;
    this._defaultTimeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  }

  // ── Public getters ─────────────────────────────────────────────
  get state() { return this._state; }
  get ready() {
    return this._state === SESSION_STATE.READY ||
           this._state === SESSION_STATE.QUERYING;
  }
  get protocol() { return this._protocol; }
  get adapterId() { return this._adapterId; }
  get profileLabel() {
    return this._transport ? this._transport.profileLabel : null;
  }
  get deviceName() {
    return this._transport ? this._transport.deviceName : null;
  }
  get transportKind() {
    return this._transport ? this._transport.kind : null;
  }

  // ── Event subscription ─────────────────────────────────────────
  onEvent(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _emit(evt) {
    for (const l of this._listeners) {
      try { l(evt); } catch (_) {}
    }
  }

  _setState(next) {
    if (this._state === next) return;
    log('state ' + this._state + ' -> ' + next);
    this._state = next;
    this._emit({ type: 'state', state: next });
  }

  // ── Transport data ingress ─────────────────────────────────────
  // Called by transport for every inbound chunk.
  _handleData(chunk) {
    if (!chunk || chunk.length === 0) return;
    this._buffer += chunk;
    this._lastActivity = Date.now();
    log('rx ' + chunk.length + 'b, buffer=' + this._buffer.length + 'b');

    // If a command is waiting, resolve it as soon as we see the '>' prompt.
    if (this._pending && this._buffer.indexOf('>') !== -1) {
      const raw = this._buffer;
      this._buffer = '';
      const p = this._pending;
      this._pending = null;
      clearTimeout(p.timer);
      log('rx done for "' + p.command + '"');
      p.resolve(raw);
    }
  }

  // ── Lifecycle ──────────────────────────────────────────────────
  async open() {
    if (this._state !== SESSION_STATE.IDLE &&
        this._state !== SESSION_STATE.CLOSED &&
        this._state !== SESSION_STATE.ERROR) {
      throw new Error('Session already open (' + this._state + ')');
    }
    this._setState(SESSION_STATE.CONNECTING);
    try {
      await this._transport.connect((chunk) => this._handleData(chunk));
      this._setState(SESSION_STATE.READY);
      log('session open — profile=' + this.profileLabel);
    } catch (err) {
      this._setState(SESSION_STATE.ERROR);
      log('session open failed: ' + (err.message || err));
      throw new Error('Connected, but could not open adapter data channel: ' +
                      (err.message || err));
    }
  }

  async close() {
    this._setState(SESSION_STATE.CLOSING);

    // Reject any in-flight command
    if (this._pending) {
      clearTimeout(this._pending.timer);
      try { this._pending.reject(new Error('Session closed')); } catch (_) {}
      this._pending = null;
    }
    // Reject any queued commands
    const queued = this._queue.splice(0, this._queue.length);
    for (const item of queued) {
      try { item.reject(new Error('Session closed')); } catch (_) {}
    }

    if (this._transport) {
      try { await this._transport.disconnect(); } catch (_) {}
    }
    this._buffer = '';
    this._running = false;
    this._setState(SESSION_STATE.CLOSED);
    log('session closed');
  }

  // ── Command queue ──────────────────────────────────────────────
  sendCommand(command, options = {}) {
    return new Promise((resolve, reject) => {
      if (this._state === SESSION_STATE.CLOSED ||
          this._state === SESSION_STATE.CLOSING) {
        reject(new Error('Cannot send: session is ' + this._state));
        return;
      }
      this._queue.push({
        command: String(command),
        options: options || {},
        resolve,
        reject,
      });
      log('queue "' + command + '" (depth=' + this._queue.length + ')');
      this._pumpQueue();
    });
  }

  async _pumpQueue() {
    if (this._running) return;
    this._running = true;
    try {
      while (this._queue.length > 0) {
        const item = this._queue.shift();
        try {
          const parsed = await this._executeOne(item.command, item.options);
          item.resolve(parsed);
        } catch (err) {
          item.reject(err);
        }
      }
    } finally {
      this._running = false;
    }
  }

  _executeOne(command, options) {
    const timeoutMs = options.timeoutMs || this._defaultTimeoutMs;

    if (!this.ready && this._state !== SESSION_STATE.CONNECTING) {
      return Promise.reject(
        new Error('Adapter not ready (state=' + this._state + ')')
      );
    }

    this._setState(SESSION_STATE.QUERYING);

    // Clear any stale buffer bytes from previous timeouts / late arrivals
    // before we write the next command.
    this._buffer = '';

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this._pending && this._pending.command === command) {
          const partial = this._buffer;
          this._buffer = '';
          this._pending = null;
          log('timeout "' + command + '" after ' + timeoutMs + 'ms' +
              (partial.length > 0 ? ' (partial ' + partial.length + 'b)' : ''));
          reject(new Error(
            'Adapter timed out responding to "' + command + '"' +
            ' after ' + timeoutMs + 'ms'
          ));
        }
      }, timeoutMs);

      this._pending = { command, timer, resolve, reject, timeoutMs };

      log('tx "' + command + '" (timeout ' + timeoutMs + 'ms)');

      // Write the command. Many ELM clones need only \r; some prefer \r\n.
      // \r alone is the documented STN/ELM line terminator.
      Promise.resolve(this._transport.write(command + '\r')).catch((err) => {
        if (this._pending && this._pending.command === command) {
          clearTimeout(this._pending.timer);
          this._pending = null;
        }
        log('tx failed "' + command + '": ' + (err.message || err));
        reject(new Error('Write failed: ' + (err.message || err)));
      });
    }).then((raw) => {
      this._setState(this._queue.length > 0
        ? SESSION_STATE.QUERYING
        : SESSION_STATE.READY);
      const parsed = parseResponse(raw, { command });
      log('parsed "' + command + '" ok=' + parsed.ok +
          (parsed.error ? ' err=' + parsed.error : '') +
          ' lines=' + parsed.lines.length);
      return parsed;
    }).catch((err) => {
      this._setState(this._queue.length > 0
        ? SESSION_STATE.QUERYING
        : SESSION_STATE.READY);
      throw err;
    });
  }

  // ── Initialization sequence ────────────────────────────────────
  async initialize(sequence = DEFAULT_INIT_SEQUENCE) {
    if (!this.ready) {
      throw new Error('Cannot initialize: session not open');
    }
    log('initialize: start (' + sequence.length + ' steps)');

    let adapterId = null;

    for (const step of sequence) {
      try {
        const result = await this.sendCommand(step.cmd, {
          timeoutMs: step.timeoutMs,
        });

        // ATZ response looks like "ELM327 v2.1" — capture it
        if (step.cmd === 'ATZ') {
          const firstText = result.lines.find(function (l) {
            return /ELM|OBD|STN/i.test(l);
          });
          if (firstText) adapterId = firstText;
        }

        if (!result.ok && !step.tolerateError) {
          throw new Error(
            'Adapter rejected "' + step.cmd + '": ' +
            (result.error || 'unknown error')
          );
        }
      } catch (err) {
        log('init step failed "' + step.cmd + '": ' + (err.message || err));
        throw new Error(
          'Adapter initialization failed at "' + step.cmd +
          '": ' + (err.message || err)
        );
      }
    }

    // Verify adapter is responsive with a lightweight query
    try {
      const proto = await this.sendCommand('ATDPN', {
        timeoutMs: DEFAULT_TIMEOUT_MS,
      });
      if (proto.ok && proto.lines.length > 0) {
        this._protocol = proto.lines[0].replace(/^A/i, '');
      }
    } catch (e) {
      log('ATDPN failed: ' + e.message + ' (non-fatal)');
    }

    this._adapterId = adapterId;
    log('initialize: done — adapter=' + (adapterId || 'unknown') +
        ' proto=' + (this._protocol || 'unknown'));

    return {
      adapter: adapterId,
      protocol: this._protocol,
    };
  }
}
