/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 *
 * ConnectScreen — connect + adapter test rig.
 *
 * Flow:
 *   idle        →  user taps "Start Scan"
 *   scanning    →  BluetoothService.scanForDevices()
 *   connecting  →  BluetoothService.connect(id, type)
 *   ready       →  session open, no commands sent yet
 *                  User can now run the smoke test or live-data loop.
 *
 * Important: we do NOT automatically send any AT commands on connect.
 * The smoke test must be explicitly triggered. This lets the user
 * see every single command and response the app sends, and makes
 * sure ATZ never runs under the hood.
 */

import React, {useState, useEffect, useCallback, useRef} from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  ActivityIndicator, ScrollView,
} from 'react-native';
import BluetoothService from '../services/BluetoothService';
import OBDService from '../services/OBDService';
import {C} from '../constants/colors';

const LOOP_ITERATIONS = 20;
const LOOP_INTERVAL_MS = 400;

function nowStamp() {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${hh}:${mm}:${ss}.${ms}`;
}

export default function ConnectScreen({navigation}) {
  const [phase, setPhase] = useState('idle');         // idle | scanning | connecting | ready
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [connInfo, setConnInfo] = useState(null);      // { name, profile, id }
  const [error, setError] = useState(null);
  const [btEnabled, setBtEnabled] = useState(true);

  // Test rig state
  const [cmdLog, setCmdLog] = useState([]);            // [{ ts, kind, text, cmd }]
  const [smokeState, setSmokeState] = useState('idle'); // idle | running | passed | failed
  const [loopState, setLoopState] = useState('idle');   // idle | running
  const [loopStats, setLoopStats] = useState(null);     // { iter, total, lastRpm, lastSpeed, lastCoolant, okCount, errCount }

  const loopCancelRef = useRef(false);
  const scrollRef = useRef(null);

  // ── Permissions + BT enabled probe ─────────────────────────────
  useEffect(() => {
    (async () => {
      const granted = await BluetoothService.requestPermissions();
      if (!granted) {
        setError('Bluetooth permissions are required. Please grant Bluetooth access in Settings.');
        return;
      }
      const enabled = await BluetoothService.isBluetoothEnabled();
      setBtEnabled(enabled);
      if (!enabled) {
        setError('Bluetooth is turned off. Enable it in your device settings.');
      }
    })();
  }, []);

  // ── Log helpers ─────────────────────────────────────────────────
  const appendLog = useCallback((entry) => {
    setCmdLog((prev) => {
      const next = prev.concat([{ ts: nowStamp(), ...entry }]);
      // cap the in-memory log so we don't grow forever
      return next.length > 400 ? next.slice(next.length - 400) : next;
    });
    // defer scroll to next tick
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollToEnd({ animated: true });
    });
  }, []);

  const clearLog = useCallback(() => setCmdLog([]), []);

  // ── Scan ────────────────────────────────────────────────────────
  const startScan = useCallback(async () => {
    setPhase('scanning');
    setError(null);
    setDevices([]);

    await BluetoothService.scanForDevices((device) => {
      setDevices((prev) => {
        if (prev.find((d) => d.id === device.id)) return prev;
        const next = [...prev, device];
        next.sort((a, b) => (b.isOBDLink ? 1 : 0) - (a.isOBDLink ? 1 : 0));
        return next;
      });
    });

    setPhase('idle');
  }, []);

  // ── Connect ─────────────────────────────────────────────────────
  const connectToDevice = useCallback(async (device) => {
    setPhase('connecting');
    setSelectedDevice(device);
    setError(null);
    clearLog();
    setSmokeState('idle');
    setLoopState('idle');
    setLoopStats(null);

    try {
      const info = await BluetoothService.connect(device.id, device.type);
      setConnInfo(info);
      setPhase('ready');
      appendLog({ kind: 'info', text: `Session open — ${info.profile || 'unknown profile'}` });
      appendLog({ kind: 'info', text: 'Tap "Run Smoke Test" to exercise the adapter.' });
    } catch (err) {
      setError(`Connect failed: ${err.message}`);
      setPhase('idle');
      setSelectedDevice(null);
    }
  }, [appendLog, clearLog]);

  // ── Smoke test ──────────────────────────────────────────────────
  const runSmokeTest = useCallback(async () => {
    if (smokeState === 'running') return;
    setSmokeState('running');
    setError(null);
    appendLog({ kind: 'info', text: '── SMOKE TEST START ──' });

    try {
      const result = await OBDService.runSmokeTest((evt) => {
        if (evt.phase === 'tx') {
          appendLog({
            kind: 'tx',
            cmd: evt.cmd,
            text: `→ ${evt.cmd}  (${evt.label}, timeout ${evt.timeoutMs}ms)`,
          });
        } else if (evt.phase === 'rx') {
          const lines = (evt.parsed && evt.parsed.lines) || [];
          const errTag = evt.parsed && evt.parsed.error ? ` [${evt.parsed.error}]` : '';
          const decoded = evt.decoded
            ? `  = ${evt.decoded.value} ${evt.decoded.unit}`
            : '';
          const body = lines.length > 0 ? lines.join(' | ') : '(no data)';
          appendLog({
            kind: (evt.parsed && evt.parsed.ok) ? 'rx' : 'rxerr',
            cmd: evt.cmd,
            text: `← ${body}${errTag}${decoded}  (${evt.elapsedMs}ms)`,
          });
        } else if (evt.phase === 'err') {
          appendLog({
            kind: 'err',
            cmd: evt.cmd,
            text: `✗ ${evt.cmd} failed: ${evt.error}  (${evt.elapsedMs}ms)`,
          });
        }
      });

      if (result.ok) {
        appendLog({ kind: 'info', text: '── SMOKE TEST PASSED ──' });
        setSmokeState('passed');
      } else {
        appendLog({
          kind: 'err',
          text: `── SMOKE TEST FAILED at ${result.failedAt}: ${result.error || 'unknown'} ──`,
        });
        setSmokeState('failed');
      }
    } catch (err) {
      appendLog({ kind: 'err', text: `Smoke test threw: ${err.message}` });
      setSmokeState('failed');
    }
  }, [smokeState, appendLog]);

  // ── Live-data loop (repeated RPM / speed / coolant reads) ──────
  const runLiveLoop = useCallback(async () => {
    if (loopState === 'running') return;
    loopCancelRef.current = false;
    setLoopState('running');
    setLoopStats({ iter: 0, total: LOOP_ITERATIONS, okCount: 0, errCount: 0 });
    appendLog({ kind: 'info', text: `── LIVE LOOP START (${LOOP_ITERATIONS} iterations) ──` });

    let okCount = 0;
    let errCount = 0;

    for (let i = 1; i <= LOOP_ITERATIONS; i++) {
      if (loopCancelRef.current) {
        appendLog({ kind: 'info', text: '── LIVE LOOP CANCELLED ──' });
        break;
      }

      try {
        const snap = await OBDService.readLiveSnapshot();
        okCount++;

        const rpmTxt = snap.rpm ? `${snap.rpm.value} ${snap.rpm.unit}` : '—';
        const spdTxt = snap.speed ? `${snap.speed.value} ${snap.speed.unit}` : '—';
        const clnTxt = snap.coolantTemp ? `${snap.coolantTemp.value} ${snap.coolantTemp.unit}` : '—';

        appendLog({
          kind: 'rx',
          text: `#${i.toString().padStart(2, '0')}  rpm=${rpmTxt}  speed=${spdTxt}  coolant=${clnTxt}  (${snap.elapsedMs}ms)`,
        });

        setLoopStats({
          iter: i,
          total: LOOP_ITERATIONS,
          okCount,
          errCount,
          lastRpm: snap.rpm,
          lastSpeed: snap.speed,
          lastCoolant: snap.coolantTemp,
        });
      } catch (err) {
        errCount++;
        appendLog({ kind: 'err', text: `#${i} FAIL: ${err.message}` });
        setLoopStats((prev) => ({ ...(prev || {}), iter: i, errCount }));
      }

      // Small pacing so the log is readable and the adapter has breathing room.
      await new Promise((r) => setTimeout(r, LOOP_INTERVAL_MS));
    }

    appendLog({
      kind: 'info',
      text: `── LIVE LOOP DONE: ${okCount}/${LOOP_ITERATIONS} ok, ${errCount} errors ──`,
    });
    setLoopState('idle');
  }, [loopState, appendLog]);

  const cancelLiveLoop = useCallback(() => {
    loopCancelRef.current = true;
  }, []);

  // ── Disconnect ─────────────────────────────────────────────────
  const disconnect = useCallback(async () => {
    try { await BluetoothService.disconnect(); } catch (_) {}
    setPhase('idle');
    setSelectedDevice(null);
    setConnInfo(null);
    setSmokeState('idle');
    setLoopState('idle');
    setLoopStats(null);
    appendLog({ kind: 'info', text: 'Disconnected' });
  }, [appendLog]);

  const proceedToScan = useCallback(() => {
    navigation.navigate('Scan', { demo: false });
  }, [navigation]);

  // ── Device list row renderer ───────────────────────────────────
  const renderDevice = ({item}) => (
    <TouchableOpacity
      style={[s.deviceRow, item.isOBDLink && s.deviceHighlight]}
      onPress={() => connectToDevice(item)}
      activeOpacity={0.7}
      disabled={phase === 'connecting'}>
      <View style={[s.deviceIcon, item.isOBDLink && s.deviceIconActive]}>
        <Text style={s.deviceIconText}>{item.isOBDLink ? '\u2B25' : '\u25CB'}</Text>
      </View>
      <View style={s.deviceInfo}>
        <Text style={s.deviceName}>{item.name}</Text>
        <Text style={s.deviceAddr}>
          {item.id?.substring(0, 17)}
          {item.rssi != null ? ` \u00B7 ${item.rssi} dBm` : ''}
          {item.type ? ` \u00B7 ${item.type.toUpperCase()}` : ''}
          {item.bonded ? ' \u00B7 Paired' : ''}
        </Text>
      </View>
      {item.isOBDLink && (
        <View style={s.obdBadge}>
          <Text style={s.obdBadgeText}>OBDLink</Text>
        </View>
      )}
    </TouchableOpacity>
  );

  // ── Render ─────────────────────────────────────────────────────
  return (
    <View style={s.container}>
      {/* Bluetooth status */}
      <View style={s.statusRow}>
        <View style={[s.statusDot, {backgroundColor: btEnabled ? C.green : C.red}]} />
        <Text style={s.statusText}>Bluetooth {btEnabled ? 'On' : 'Off'}</Text>
      </View>

      {/* Connected banner */}
      {phase === 'ready' && (
        <View style={s.connectedBanner}>
          <View style={s.connectedDot} />
          <View style={{flex: 1}}>
            <Text style={s.connectedText}>
              Connected to {selectedDevice?.name || connInfo?.name}
            </Text>
            <Text style={s.protoText}>
              {connInfo?.profile || 'unknown'}
              {OBDService.adapterId ? ' \u00B7 ' + OBDService.adapterId : ''}
              {OBDService.protocol ? ' \u00B7 proto ' + OBDService.protocol : ''}
            </Text>
          </View>
          <TouchableOpacity style={s.disconnectBtn} onPress={disconnect}>
            <Text style={s.disconnectText}>Disconnect</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Error */}
      {error && (
        <View style={s.errorBanner}>
          <Text style={s.errorIcon}>!</Text>
          <Text style={s.errorText}>{error}</Text>
        </View>
      )}

      {/* ── Pre-connect view: device list ───────────────────────── */}
      {phase !== 'ready' && (
        <>
          <Text style={s.sectionTitle}>
            {phase === 'scanning'
              ? 'Scanning for devices...'
              : devices.length > 0
                ? `Found ${devices.length} device${devices.length !== 1 ? 's' : ''}`
                : 'Tap Start Scan to find your OBDLink'}
          </Text>

          <FlatList
            data={devices}
            keyExtractor={(item) => item.id}
            renderItem={renderDevice}
            style={s.list}
            contentContainerStyle={devices.length === 0 ? {flex: 1} : {}}
            ListEmptyComponent={
              phase !== 'scanning' ? (
                <View style={s.emptyWrap}>
                  <Text style={s.emptyIcon}>{'\u2B25'}</Text>
                  <Text style={s.emptyText}>
                    Plug your OBDLink MX+ into the OBD-II port under your dashboard, then tap Start Scan.
                  </Text>
                </View>
              ) : null
            }
          />

          <View style={s.actions}>
            {phase === 'scanning' ? (
              <View style={s.loadingRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.loadingText}>Scanning for devices...</Text>
              </View>
            ) : phase === 'connecting' ? (
              <View style={s.loadingRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.loadingText}>
                  Opening session to {selectedDevice?.name}...
                </Text>
              </View>
            ) : (
              <TouchableOpacity style={s.scanBtn} onPress={startScan} activeOpacity={0.85}>
                <Text style={s.scanBtnText}>Start Scan</Text>
              </TouchableOpacity>
            )}
          </View>
        </>
      )}

      {/* ── Post-connect view: adapter test rig ─────────────────── */}
      {phase === 'ready' && (
        <>
          {/* Action buttons */}
          <View style={s.testBtnRow}>
            <TouchableOpacity
              style={[
                s.primaryTestBtn,
                smokeState === 'running' && s.btnDisabled,
              ]}
              onPress={runSmokeTest}
              disabled={smokeState === 'running' || loopState === 'running'}
              activeOpacity={0.85}>
              {smokeState === 'running' ? (
                <View style={s.loadingRow}>
                  <ActivityIndicator size="small" color="#fff" />
                  <Text style={s.primaryTestText}>Running smoke test...</Text>
                </View>
              ) : (
                <Text style={s.primaryTestText}>
                  {smokeState === 'passed' ? '\u2713 Re-run Smoke Test' :
                   smokeState === 'failed' ? '↻ Re-run Smoke Test' :
                   'Run Smoke Test'}
                </Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                s.secondaryTestBtn,
                (smokeState !== 'passed' || loopState === 'running') && s.btnDisabled,
              ]}
              onPress={loopState === 'running' ? cancelLiveLoop : runLiveLoop}
              disabled={smokeState !== 'passed' && loopState !== 'running'}
              activeOpacity={0.85}>
              <Text style={s.secondaryTestText}>
                {loopState === 'running'
                  ? `Cancel Loop  (${loopStats?.iter || 0}/${LOOP_ITERATIONS})`
                  : 'Loop Live Data (RPM / Speed / Coolant) ×20'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Live snapshot mini-display */}
          {loopStats && (
            <View style={s.liveGrid}>
              <View style={s.liveBox}>
                <Text style={s.liveLabel}>RPM</Text>
                <Text style={s.liveValue}>
                  {loopStats.lastRpm ? Math.round(loopStats.lastRpm.value) : '—'}
                </Text>
              </View>
              <View style={s.liveBox}>
                <Text style={s.liveLabel}>SPEED</Text>
                <Text style={s.liveValue}>
                  {loopStats.lastSpeed ? loopStats.lastSpeed.value : '—'}
                </Text>
              </View>
              <View style={s.liveBox}>
                <Text style={s.liveLabel}>COOLANT</Text>
                <Text style={s.liveValue}>
                  {loopStats.lastCoolant ? loopStats.lastCoolant.value : '—'}
                </Text>
              </View>
              <View style={s.liveBox}>
                <Text style={s.liveLabel}>OK / ERR</Text>
                <Text style={s.liveValue}>
                  {loopStats.okCount || 0} / {loopStats.errCount || 0}
                </Text>
              </View>
            </View>
          )}

          {/* Command log */}
          <View style={s.logCard}>
            <View style={s.logHeader}>
              <Text style={s.logTitle}>COMMAND LOG</Text>
              <TouchableOpacity onPress={clearLog}>
                <Text style={s.logClear}>clear</Text>
              </TouchableOpacity>
            </View>
            <ScrollView
              ref={scrollRef}
              style={s.logScroll}
              contentContainerStyle={{paddingVertical: 4}}>
              {cmdLog.length === 0 ? (
                <Text style={s.logEmpty}>No commands yet. Tap "Run Smoke Test".</Text>
              ) : (
                cmdLog.map((e, i) => (
                  <Text
                    key={i}
                    style={[
                      s.logLine,
                      e.kind === 'tx' && s.logTx,
                      e.kind === 'rx' && s.logRx,
                      e.kind === 'rxerr' && s.logRxErr,
                      e.kind === 'err' && s.logErr,
                      e.kind === 'info' && s.logInfo,
                    ]}>
                    [{e.ts}] {e.text}
                  </Text>
                ))
              )}
            </ScrollView>
          </View>

          {/* Advanced: proceed to vehicle scan (disabled until smoke test passes) */}
          {smokeState === 'passed' && (
            <TouchableOpacity
              style={s.proceedBtn}
              onPress={proceedToScan}
              activeOpacity={0.85}>
              <Text style={s.proceedText}>Continue to Vehicle Scan →</Text>
            </TouchableOpacity>
          )}
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: C.bg, padding: 16},

  statusRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12,
  },
  statusDot: {width: 8, height: 8, borderRadius: 4},
  statusText: {color: C.textDim, fontSize: 13, fontWeight: '500'},

  sectionTitle: {
    color: C.textBright, fontSize: 18, fontWeight: '700',
    marginBottom: 12, marginTop: 8,
  },

  list: {flex: 1},

  // Device rows
  deviceRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.card, borderRadius: 12,
    padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: C.border,
  },
  deviceHighlight: {
    borderColor: C.accent, borderLeftWidth: 3, borderLeftColor: C.accent,
  },
  deviceIcon: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: C.border,
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  deviceIconActive: {backgroundColor: C.accentDim},
  deviceIconText: {color: C.accent, fontSize: 16, fontWeight: '700'},
  deviceInfo: {flex: 1},
  deviceName: {color: C.textBright, fontSize: 15, fontWeight: '600'},
  deviceAddr: {color: C.textDim, fontSize: 12, marginTop: 2},
  obdBadge: {
    backgroundColor: C.accentDim, borderRadius: 6,
    paddingHorizontal: 10, paddingVertical: 4,
    borderWidth: 1, borderColor: C.accentMid,
  },
  obdBadgeText: {color: C.accent, fontSize: 11, fontWeight: '700'},

  emptyWrap: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32},
  emptyIcon: {color: C.border, fontSize: 40, marginBottom: 12},
  emptyText: {
    color: C.textDim, fontSize: 14, textAlign: 'center', lineHeight: 22,
  },

  actions: {paddingVertical: 16},
  scanBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    padding: 16, alignItems: 'center',
    shadowColor: C.accent, shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 6,
  },
  scanBtnText: {color: '#fff', fontSize: 16, fontWeight: '700', letterSpacing: 0.3},
  loadingRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    padding: 10, gap: 10,
  },
  loadingText: {color: C.accent, fontSize: 15, fontWeight: '600'},

  // Connected banner
  connectedBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.greenDim, borderRadius: 12, padding: 12,
    marginBottom: 12, borderWidth: 1, borderColor: C.green, gap: 10,
  },
  connectedDot: {width: 10, height: 10, borderRadius: 5, backgroundColor: C.green},
  connectedText: {color: C.green, fontSize: 14, fontWeight: '700'},
  protoText: {color: C.textDim, fontSize: 11, marginTop: 2},
  disconnectBtn: {
    backgroundColor: C.redDim, borderWidth: 1, borderColor: C.red,
    borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6,
  },
  disconnectText: {color: C.red, fontSize: 11, fontWeight: '700'},

  // Error banner
  errorBanner: {
    flexDirection: 'row', alignItems: 'flex-start',
    backgroundColor: C.redDim, borderRadius: 12, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: C.red, gap: 10,
  },
  errorIcon: {
    color: C.red, fontSize: 16, fontWeight: '800',
    width: 22, height: 22, textAlign: 'center', lineHeight: 22,
    borderWidth: 1.5, borderColor: C.red, borderRadius: 11,
  },
  errorText: {color: C.red, fontSize: 14, flex: 1, lineHeight: 20},

  // Test rig buttons
  testBtnRow: {gap: 10, marginBottom: 12},
  primaryTestBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    paddingVertical: 14, alignItems: 'center',
  },
  primaryTestText: {color: '#fff', fontSize: 15, fontWeight: '700', letterSpacing: 0.3},
  secondaryTestBtn: {
    backgroundColor: C.card, borderRadius: 12,
    paddingVertical: 12, alignItems: 'center',
    borderWidth: 1, borderColor: C.accentMid,
  },
  secondaryTestText: {color: C.accent, fontSize: 14, fontWeight: '600'},
  btnDisabled: {opacity: 0.45},

  // Live grid
  liveGrid: {
    flexDirection: 'row', gap: 8, marginBottom: 12,
  },
  liveBox: {
    flex: 1,
    backgroundColor: C.card, borderRadius: 8, padding: 10,
    borderWidth: 1, borderColor: C.border,
    alignItems: 'center',
  },
  liveLabel: {color: C.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 1},
  liveValue: {color: C.textBright, fontSize: 18, fontWeight: '800', marginTop: 2},

  // Log
  logCard: {
    flex: 1,
    backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border,
    padding: 10, marginBottom: 10,
  },
  logHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 6,
  },
  logTitle: {
    color: C.textDim, fontSize: 11, fontWeight: '700',
    letterSpacing: 1,
  },
  logClear: {color: C.accent, fontSize: 11, fontWeight: '600'},
  logScroll: {flex: 1},
  logEmpty: {color: C.textDim, fontSize: 12, fontStyle: 'italic'},
  logLine: {
    color: C.text, fontSize: 11,
    fontFamily: 'monospace', lineHeight: 16,
  },
  logTx: {color: C.accent},
  logRx: {color: C.textBright},
  logRxErr: {color: C.amber},
  logErr: {color: C.red},
  logInfo: {color: C.textDim, fontStyle: 'italic'},

  // Proceed
  proceedBtn: {
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
    borderRadius: 10, paddingVertical: 12, alignItems: 'center',
  },
  proceedText: {color: C.textDim, fontSize: 13, fontWeight: '600'},
});
