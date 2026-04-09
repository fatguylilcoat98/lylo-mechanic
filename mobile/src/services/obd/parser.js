/*
 * LYLO Mechanic — OBDLink / ELM327 / STN11xx response parser
 *
 * Pure functions. No React Native dependencies.
 * Safe to require() from Node for tests.
 *
 * Responsibilities:
 *   - Normalize CR/LF/prompt/whitespace
 *   - Strip echoed command (when ATE1 mode leaks through)
 *   - Strip SEARCHING... transients
 *   - Recognize adapter error tokens
 *   - Classify each line (hex | ok | error | text | empty)
 *   - Extract hex data bytes for OBD PID responses
 *
 * parseResponse(raw, { command }) returns:
 *   {
 *     ok:          boolean,     // false if any adapter error token matched
 *     terminated:  boolean,     // true if raw contained a '>' prompt marker
 *     raw:         string,      // the raw input
 *     lines:       string[],    // cleaned lines, no echo, no SEARCHING, no prompt
 *     error:       string|null, // adapter error token if detected
 *   }
 */

'use strict';

// Tokens the adapter uses to signal an error or non-data response.
// Order matters for startsWith — put longer tokens first when they
// share a prefix.
const ERROR_TOKENS = [
  'UNABLE TO CONNECT',
  'NO DATA',
  'CAN ERROR',
  'BUS ERROR',
  'BUS BUSY',
  'BUS INIT',
  'DATA ERROR',
  'BUFFER FULL',
  'FB ERROR',
  'LV RESET',
  'LP ALERT',
  'ACT ALERT',
  '<RX ERROR>',
  'STOPPED',
  'ERROR',
  '?',
];

function containsPrompt(raw) {
  return typeof raw === 'string' && raw.indexOf('>') !== -1;
}

function normalizeCommand(cmd) {
  return String(cmd || '').toUpperCase().replace(/\s+/g, '');
}

function classifyLine(line) {
  const upper = String(line || '').toUpperCase().trim();
  if (upper === '') return 'empty';
  if (upper === 'OK') return 'ok';
  if (upper === 'SEARCHING...' || upper === 'SEARCHING') return 'searching';
  for (const tok of ERROR_TOKENS) {
    if (upper === tok || upper.startsWith(tok)) return 'error';
  }
  // Hex payload: hex chars + optional spaces + colons (CAN header)
  if (/^[0-9A-F:\s]+$/i.test(line) && /[0-9A-F]/i.test(line)) return 'hex';
  return 'text';
}

function parseResponse(raw, opts) {
  const options = opts || {};
  const command = options.command || null;
  const input = typeof raw === 'string' ? raw : '';

  const terminated = containsPrompt(input);

  // Normalize: CR->LF, drop NULs, drop prompt
  const text = input
    .replace(/\r/g, '\n')
    .replace(/\u0000/g, '')
    .replace(/>/g, '')
    .trim();

  // Split to lines, trim, drop empties
  let lines = text
    .split('\n')
    .map(function (l) { return l.trim(); })
    .filter(function (l) { return l.length > 0; });

  // Drop echoed command if ATE1 leaked through
  if (command) {
    const normCmd = normalizeCommand(command);
    lines = lines.filter(function (l) {
      return normalizeCommand(l) !== normCmd;
    });
  }

  // Drop SEARCHING... transient
  lines = lines.filter(function (l) {
    return classifyLine(l) !== 'searching';
  });

  // Detect first error line
  let error = null;
  for (const line of lines) {
    if (classifyLine(line) === 'error') {
      error = line.toUpperCase().trim();
      break;
    }
  }

  return {
    ok: error === null,
    terminated: terminated,
    raw: input,
    lines: lines,
    error: error,
  };
}

/**
 * Extract the data-byte array from a Mode 01/09 response.
 *
 *   parsed: the object returned by parseResponse
 *   expectedMode: the response-mode byte as a 2-char hex string
 *                 ('41' for mode 01, '49' for mode 09, '43' for mode 03, etc.)
 *   expectedPid:  the 2-char hex PID, or null if no PID (mode 03/07)
 *
 * Returns array of ints, or null if no matching line.
 */
function extractHexBytes(parsed, expectedMode, expectedPid) {
  if (!parsed || !parsed.ok || !parsed.lines) return null;

  const prefix = (String(expectedMode || '') + String(expectedPid || ''))
    .toUpperCase();

  for (const line of parsed.lines) {
    const hex = line.replace(/\s+/g, '').toUpperCase();
    if (hex.length < prefix.length) continue;
    if (!hex.startsWith(prefix)) continue;
    const dataHex = hex.slice(prefix.length);
    const bytes = [];
    for (let i = 0; i + 2 <= dataHex.length; i += 2) {
      const v = parseInt(dataHex.substr(i, 2), 16);
      if (Number.isNaN(v)) return null;
      bytes.push(v);
    }
    return bytes;
  }
  return null;
}

module.exports = {
  ERROR_TOKENS: ERROR_TOKENS,
  containsPrompt: containsPrompt,
  classifyLine: classifyLine,
  parseResponse: parseResponse,
  extractHexBytes: extractHexBytes,
};
