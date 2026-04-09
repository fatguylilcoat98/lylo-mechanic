/*
 * LYLO Mechanic — Parser tests
 *
 * Plain Node test harness. Run with:
 *   node mobile/src/services/obd/parser.test.js
 *
 * No jest / mocha / babel required.
 */

'use strict';

const assert = require('assert');
const {
  parseResponse,
  classifyLine,
  containsPrompt,
  extractHexBytes,
} = require('./parser');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log('  PASS ' + name);
  } catch (e) {
    failed++;
    console.error('  FAIL ' + name);
    console.error('       ' + (e.message || e));
  }
}

console.log('Running parser tests...\n');

test('containsPrompt detects > terminator', function () {
  assert.strictEqual(containsPrompt('OK\r>'), true);
  assert.strictEqual(containsPrompt('OK\r'), false);
  assert.strictEqual(containsPrompt(''), false);
  assert.strictEqual(containsPrompt(null), false);
});

test('classifyLine recognizes adapter errors', function () {
  assert.strictEqual(classifyLine('NO DATA'), 'error');
  assert.strictEqual(classifyLine('UNABLE TO CONNECT'), 'error');
  assert.strictEqual(classifyLine('STOPPED'), 'error');
  assert.strictEqual(classifyLine('BUS INIT: ...ERROR'), 'error');
  assert.strictEqual(classifyLine('?'), 'error');
  assert.strictEqual(classifyLine('CAN ERROR'), 'error');
});

test('classifyLine recognizes hex lines', function () {
  assert.strictEqual(classifyLine('41 0C 1A F8'), 'hex');
  assert.strictEqual(classifyLine('410C1AF8'), 'hex');
  assert.strictEqual(classifyLine('7E8 03 41 0C 1A F8'), 'hex');
});

test('classifyLine recognizes OK and SEARCHING', function () {
  assert.strictEqual(classifyLine('OK'), 'ok');
  assert.strictEqual(classifyLine('SEARCHING...'), 'searching');
});

test('parseResponse cleans a good PID response', function () {
  const raw = '010C\r41 0C 1A F8\r\r>';
  const parsed = parseResponse(raw, { command: '010C' });
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.terminated, true);
  assert.strictEqual(parsed.error, null);
  assert.deepStrictEqual(parsed.lines, ['41 0C 1A F8']);
});

test('parseResponse handles NO DATA', function () {
  const parsed = parseResponse('NO DATA\r\r>', { command: '0105' });
  assert.strictEqual(parsed.ok, false);
  assert.strictEqual(parsed.error, 'NO DATA');
});

test('parseResponse drops SEARCHING transient', function () {
  const raw = '0100\rSEARCHING...\r41 00 BE 3F A8 13\r\r>';
  const parsed = parseResponse(raw, { command: '0100' });
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.lines.length, 1);
  assert.strictEqual(parsed.lines[0], '41 00 BE 3F A8 13');
});

test('parseResponse strips echoed command', function () {
  const raw = 'ATZ\rELM327 v2.1\r\r>';
  const parsed = parseResponse(raw, { command: 'ATZ' });
  assert.strictEqual(parsed.ok, true);
  assert.deepStrictEqual(parsed.lines, ['ELM327 v2.1']);
});

test('parseResponse handles malformed empty input', function () {
  const parsed = parseResponse('', { command: '010C' });
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.terminated, false);
  assert.deepStrictEqual(parsed.lines, []);
});

test('parseResponse handles UNABLE TO CONNECT', function () {
  const parsed = parseResponse('UNABLE TO CONNECT\r>', { command: '0100' });
  assert.strictEqual(parsed.ok, false);
  assert.strictEqual(parsed.error, 'UNABLE TO CONNECT');
});

test('parseResponse handles STOPPED', function () {
  const parsed = parseResponse('STOPPED\r>', { command: '010C' });
  assert.strictEqual(parsed.ok, false);
  assert.strictEqual(parsed.error, 'STOPPED');
});

test('extractHexBytes pulls Mode01 PID0C bytes', function () {
  const parsed = parseResponse('41 0C 1A F8\r>', { command: '010C' });
  const bytes = extractHexBytes(parsed, '41', '0C');
  assert.deepStrictEqual(bytes, [0x1A, 0xF8]);
});

test('extractHexBytes pulls compact no-space bytes', function () {
  const parsed = parseResponse('410D5A\r>', { command: '010D' });
  const bytes = extractHexBytes(parsed, '41', '0D');
  assert.deepStrictEqual(bytes, [0x5A]);
});

test('extractHexBytes returns null for non-matching prefix', function () {
  const parsed = parseResponse('7F 01 12\r>', { command: '010C' });
  const bytes = extractHexBytes(parsed, '41', '0C');
  assert.strictEqual(bytes, null);
});

test('extractHexBytes returns null on error response', function () {
  const parsed = parseResponse('NO DATA\r>', { command: '010C' });
  const bytes = extractHexBytes(parsed, '41', '0C');
  assert.strictEqual(bytes, null);
});

test('parseResponse handles multi-line VIN response', function () {
  const raw =
    '014\r0: 49 02 01 31 47 31\r1: 4A 43 35 32 34 34\r2: 52 37 32 35 32 35 36\r\r>';
  const parsed = parseResponse(raw, { command: '0902' });
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.lines.length >= 3, true);
});

console.log('\n' + passed + ' passed, ' + failed + ' failed');
if (failed > 0) process.exit(1);
