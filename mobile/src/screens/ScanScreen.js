/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React, {useState, useEffect, useRef} from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import OBDService from '../services/OBDService';
import ApiClient from '../services/ApiClient';
import {C} from '../constants/colors';


// Embedded demo result — works offline with zero Bluetooth and zero API
const DEMO_RESULT = {
  input: 'P0420',
  input_type: 'demo',
  results: [{
    code: 'P0420',
    whats_wrong: {
      summary: 'Catalyst System Efficiency Below Threshold (Bank 1)',
      likely_cause: 'Exhaust Manifold / Header Leak',
      explanation: 'A leak upstream of the O2 sensors introduces extra oxygen, causing the sensor to read lean and falsely flag catalyst inefficiency. This is the most commonly missed cause of P0420.',
      other_possibilities: ['Faulty Downstream O2 Sensor', 'Catalytic Converter Degradation'],
      check_first: ['Inspect for exhaust leaks by listening for ticking at cold start', 'Check for exhaust smell at startup'],
    },
    urgency: {level: 'SAFE TO DRIVE', color: 'green', message: 'You can keep driving, but schedule a repair to avoid bigger issues.'},
    cost: {diy: '$35 – $100', shop: '$165 – $480', dealer: '$300 – $700', note: 'Prices are US national averages.'},
    difficulty: {level: 'Medium', label: 'Experienced DIY or shop'},
    shop_script: '"I\'m getting code P0420. I understand it could be an exhaust leak or O2 sensor issue, not necessarily the catalytic converter. Can you run a diagnostic to confirm before replacing anything? I\'m expecting the repair to be in the $165 – $480 range — does that sound right?"',
    red_flags: [
      'If they immediately recommend catalytic converter replacement without testing O2 sensors and checking for exhaust leaks first — that\'s a red flag. P0420 is the most misdiagnosed code in the industry.',
      'Broken studs requiring drilling/extraction can double the repair cost',
    ],
  }],
};

const DEMO_VEHICLE = {
  year: '2017', make: 'Honda', model: 'Civic',
  engine: '1.5L Turbo', odometer: '87000',
};

const EMPTY_VEHICLE = {
  year: '', make: '', model: '',
  engine: '', odometer: '',
};

const STAGES = [
  {key: 'init', label: 'Initializing OBD...', icon: '\u{1F50C}'},
  {key: 'codes', label: 'Reading fault codes...', icon: '\u{1F50D}'},
  {key: 'pids', label: 'Reading sensor data...', icon: '\u{1F4CA}'},
  {key: 'analyze', label: 'Analyzing with LYLO...', icon: '\u{1F9E0}'},
  {key: 'script', label: 'Generating ShopScript...', icon: '\u{1F5E3}'},
];

let scanCounter = 0; // Module-level counter survives re-renders

export default function ScanScreen({route, navigation}) {
  const isDemo = route.params?.demo ?? false;
  const [phase, setPhase] = useState('vehicle'); // vehicle | scanning | sending | done
  const [progress, setProgress] = useState({step: 0, total: 0, msg: ''});
  const [stageIdx, setStageIdx] = useState(0);
  const [log, setLog] = useState([]);
  const [scanData, setScanData] = useState(null);
  const [vehicle, setVehicle] = useState(isDemo ? DEMO_VEHICLE : EMPTY_VEHICLE);
  const [vinStatus, setVinStatus] = useState(isDemo ? 'demo' : 'pending'); // pending | reading | done | failed | demo
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const scanInProgress = useRef(false);

  // Auto-read VIN when connected to real OBD adapter
  useEffect(() => {
    if (isDemo) return;
    let cancelled = false;

    (async () => {
      setVinStatus('reading');
      try {
        const vin = await OBDService.readVIN();
        if (cancelled) return;

        if (vin) {
          addLog(`VIN: ${vin}`, 'success');
          const decoded = await OBDService.decodeVIN(vin);
          if (cancelled) return;

          if (decoded) {
            setVehicle({
              year: decoded.year,
              make: decoded.make,
              model: decoded.model,
              engine: decoded.engine,
              odometer: '',
              vin: decoded.vin,
            });
            setVinStatus('done');
            addLog(`Vehicle: ${decoded.year} ${decoded.make} ${decoded.model} ${decoded.engine}`, 'success');
          } else {
            setVehicle(prev => ({...prev, vin}));
            setVinStatus('done');
            addLog('VIN read but decode failed — enter vehicle info manually', 'warn');
          }
        } else {
          setVinStatus('failed');
          addLog('VIN not available — enter vehicle info manually', 'warn');
        }
      } catch (e) {
        if (!cancelled) {
          setVinStatus('failed');
          addLog(`VIN read error: ${e.message}`, 'warn');
        }
      }
    })();

    return () => { cancelled = true; };
  }, [isDemo]);

  const addLog = (msg, type = 'info') => {
    const ts = new Date().toLocaleTimeString('en-US', {
      hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    setLog(prev => [...prev, {ts, msg, type}]);
  };

  const startScan = async () => {
    scanCounter++;
    const thisScan = scanCounter;
    const tag = `[SCAN #${thisScan}]`;

    // ── Race condition guard ──
    if (scanInProgress.current) {
      console.warn(tag, 'BLOCKED — scan already in progress!');
      addLog(`${tag} BLOCKED — previous scan still running!`, 'error');
      return;
    }
    scanInProgress.current = true;

    // ── Log state BEFORE reset ──
    console.log(tag, '===== SCAN START =====');
    console.log(tag, 'State BEFORE reset:', {
      phase,
      stageIdx,
      progress,
      scanData: scanData ? `object with keys: ${Object.keys(scanData).join(',')}` : null,
      scanData_raw_dtcs: scanData?.raw_dtcs ? JSON.stringify(scanData.raw_dtcs) : null,
      error,
      logLength: log.length,
      'OBDService._initialized': OBDService.initialized,
      'OBDService._protocol': OBDService.protocol,
    });
    addLog(`${tag} Starting — previous scanData: ${scanData ? 'EXISTS' : 'null'}`, 'info');

    // ── Reset ALL state ──
    setPhase('scanning');
    setError(null);
    setStageIdx(0);
    setScanData(null);
    setProgress({step: 0, total: 0, msg: ''});

    console.log(tag, 'State reset complete (scanData cleared, progress zeroed)');

    if (isDemo) {
      addLog('Demo mode — P0420 catalytic converter scenario', 'info');
      setPhase('sending');
      setStageIdx(3);
      addLog('Running quick check...', 'info');

      let result;
      try {
        const alive = await ApiClient.ping();
        if (alive) {
          addLog('Backend connected — running quick check...', 'info');
          result = await ApiClient.quickCheck('P0420');
        } else {
          addLog('Backend offline — using embedded demo data', 'info');
          result = DEMO_RESULT;
        }
      } catch (err) {
        addLog('Backend unavailable — using embedded demo data', 'info');
        result = DEMO_RESULT;
      }

      await new Promise(r => setTimeout(r, 800));
      setStageIdx(4);
      addLog('Diagnosis complete.', 'success');
      await new Promise(r => setTimeout(r, 400));
      scanInProgress.current = false;
      navigation.replace('Results', {result});
      return;
    }

    // Live OBD scan
    try {
      console.log(tag, 'OBDService state:', {
        initialized: OBDService.initialized,
        protocol: OBDService.protocol,
      });
      addLog(`${tag} OBD initialized=${OBDService.initialized} proto=${OBDService.protocol}`, 'info');
      addLog(`${tag} Starting OBD-II full vehicle scan...`, 'info');
      setStageIdx(1);

      const scanStartTime = Date.now();
      const data = await OBDService.fullScan((step, total, msg) => {
        setProgress({step, total, msg});
        addLog(msg, 'info');
        if (step <= 1) setStageIdx(0);
        else if (step <= 3) setStageIdx(1);
        else setStageIdx(2);
      });
      const scanDuration = Date.now() - scanStartTime;

      // ── Log DTC array immediately after scan ──
      console.log(tag, `fullScan() completed in ${scanDuration}ms`);
      console.log(tag, 'raw_dtcs from OBD:', JSON.stringify(data?.raw_dtcs));
      console.log(tag, 'raw_pids keys:', Object.keys(data?.raw_pids || {}));
      console.log(tag, 'pending_codes:', JSON.stringify(data?.pending_codes));
      console.log(tag, 'mil_status:', data?.mil_status, 'dtc_count:', data?.dtc_count);
      console.log(tag, 'FULL DATA:', JSON.stringify(data));

      addLog(`${tag} Scan took ${scanDuration}ms`, 'info');
      addLog(`${tag} DTCs from OBD: ${JSON.stringify(data?.raw_dtcs)}`, 'info');

      setScanData(data);
      addLog(`Scan complete: ${data.raw_dtcs.length} DTCs, ${Object.keys(data.raw_pids).length} PIDs`, 'success');

      if (data.mil_status) {
        addLog('Check Engine Light is ON', 'warn');
      }
      if (data.raw_dtcs.length > 0) {
        addLog(`Fault codes: ${data.raw_dtcs.map(d => d.code).join(', ')}`, 'warn');
      } else {
        addLog('No stored fault codes found.', 'success');
      }

      // Send DTCs through quick-check MVP endpoint
      setPhase('sending');
      setStageIdx(3);
      addLog('Analyzing codes with LYLO...', 'info');

      // Pre-warm: wake Render if cold + refresh stale connection pool
      const pingOk = await ApiClient.ping();
      console.log(tag, 'Pre-warm ping:', pingOk ? 'OK' : 'FAILED');
      addLog(`${tag} Backend ping: ${pingOk ? 'connected' : 'cold start, retrying...'}`, 'info');

      // ── Pre-POST data validation ──
      const dtcCodes = (data?.raw_dtcs || []).map(d => d?.code).filter(Boolean);
      const inputStr = dtcCodes.join(' ');
      console.log(tag, '===== PRE-POST CHECK =====');
      console.log(tag, 'typeof data:', typeof data);
      console.log(tag, 'data === null:', data === null);
      console.log(tag, 'raw_dtcs is array:', Array.isArray(data?.raw_dtcs));
      console.log(tag, 'raw_dtcs length:', data?.raw_dtcs?.length);
      console.log(tag, 'Extracted DTC codes:', JSON.stringify(dtcCodes));
      console.log(tag, 'POST input string:', JSON.stringify(inputStr));
      console.log(tag, 'Will hit canned response:', dtcCodes.length === 0);

      addLog(`${tag} POST input: "${inputStr}" (${dtcCodes.length} codes)`, 'info');

      let result;
      try {
        const postStart = Date.now();
        result = await ApiClient.quickCheckFromScan(data);
        const postDuration = Date.now() - postStart;

        console.log(tag, `quickCheckFromScan SUCCESS in ${postDuration}ms`);
        console.log(tag, 'Response keys:', Object.keys(result || {}));
        addLog(`${tag} API responded in ${postDuration}ms`, 'success');
      } catch (fetchErr) {
        const postDuration = Date.now() - scanStartTime;
        console.error(tag, '===== QUICK CHECK FAILED =====');
        console.error(tag, 'Failed after total', postDuration, 'ms');
        console.error(tag, 'error.name:', fetchErr.name);
        console.error(tag, 'error.message:', fetchErr.message);
        console.error(tag, 'error.code:', fetchErr.code);
        console.error(tag, 'error.type:', fetchErr.type);
        console.error(tag, 'error.cause:', fetchErr.cause);
        console.error(tag, 'error.stack:', fetchErr.stack);
        console.error(tag, 'Full error:', JSON.stringify(fetchErr, Object.getOwnPropertyNames(fetchErr)));
        console.error(tag, 'Data that was being sent:', JSON.stringify({input: inputStr}));
        addLog(`${tag} FAIL: ${fetchErr.name}: ${fetchErr.message}`, 'error');
        addLog(`${tag} code=${fetchErr.code} type=${fetchErr.type}`, 'error');
        addLog(`${tag} Was sending: {"input":"${inputStr}"}`, 'error');
        if (fetchErr._lyloDebug) {
          const d = fetchErr._lyloDebug;
          addLog(`${tag} Phase: ${d.phase}`, 'error');
          addLog(`${tag} HTTP status: ${d.status || 'N/A (fetch threw before response)'}`, 'error');
          addLog(`${tag} Response body: ${(d.responseBody || 'none').slice(0, 300)}`, 'error');
          addLog(`${tag} Request body: ${d.requestBody}`, 'error');
          addLog(`${tag} API instanceId: ${d.instanceId}`, 'error');
        } else {
          addLog(`${tag} No _lyloDebug — error thrown outside instrumented path`, 'error');
        }
        addLog(`${tag} Stack: ${(fetchErr.stack || '').slice(0, 300)}`, 'error');
        throw fetchErr;
      }

      setStageIdx(4);
      addLog('Diagnosis complete — ShopScript ready.', 'success');

      scanInProgress.current = false;
      navigation.replace('Results', {result});
    } catch (err) {
      console.error(tag, 'Outer catch:', err.message);
      setError(`Scan failed: ${err.message}`);
      addLog(`${tag} OUTER ERROR: ${err.message}`, 'error');
      setPhase('vehicle');
      scanInProgress.current = false;
    }
  };

  const progressPct = progress.total > 0
    ? Math.round((progress.step / progress.total) * 100)
    : 0;

  return (
    <View style={s.container}>
      {/* Vehicle info */}
      {phase === 'vehicle' && (
        <View style={s.vehicleCard}>
          <Text style={s.cardLabel}>
            {vinStatus === 'reading' ? 'READING VIN...' : 'VEHICLE'}
          </Text>

          {vinStatus === 'reading' && (
            <View style={s.vinReadingRow}>
              <ActivityIndicator size="small" color={C.accent} />
              <Text style={s.vinReadingText}>Reading VIN from vehicle...</Text>
            </View>
          )}

          {(vinStatus === 'done' || vinStatus === 'demo') && vehicle.make ? (
            <View>
              <Text style={s.vehicleText}>
                {vehicle.year} {vehicle.make} {vehicle.model}
              </Text>
              <Text style={s.vehicleDetail}>
                {[vehicle.engine, vehicle.vin].filter(Boolean).join(' \u00B7 ')}
              </Text>
            </View>
          ) : vinStatus === 'failed' ? (
            <Text style={s.vehicleDetail}>
              Could not read VIN — vehicle info will be sent without it
            </Text>
          ) : vinStatus !== 'reading' ? (
            <Text style={s.vehicleDetail}>
              Connect to OBDLink to auto-detect vehicle
            </Text>
          ) : null}

          {error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          <TouchableOpacity
            style={[s.scanBtn, vinStatus === 'reading' && {opacity: 0.5}]}
            onPress={startScan}
            activeOpacity={0.85}
            disabled={vinStatus === 'reading'}>
            <Text style={s.scanBtnText}>
              {isDemo ? 'Run Demo Scan' : 'Scan Vehicle'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Progress with stages */}
      {(phase === 'scanning' || phase === 'sending') && (
        <View style={s.progressCard}>
          <ActivityIndicator size="large" color={C.accent} />
          <Text style={s.progressTitle}>
            {phase === 'scanning' ? 'Scanning Vehicle...' : 'Analyzing...'}
          </Text>

          {/* Stage indicators */}
          <View style={s.stagesWrap}>
            {STAGES.map((stage, i) => (
              <View key={stage.key} style={[
                s.stageRow,
                i <= stageIdx && s.stageActive,
                i < stageIdx && s.stageDone,
              ]}>
                <Text style={s.stageIcon}>
                  {i < stageIdx ? '\u2705' : stage.icon}
                </Text>
                <Text style={[
                  s.stageLabel,
                  i <= stageIdx && {color: C.textBright},
                  i < stageIdx && {color: C.green},
                ]}>
                  {stage.label}
                </Text>
              </View>
            ))}
          </View>

          {phase === 'scanning' && progress.total > 0 && (
            <View style={s.progressBarWrap}>
              <View style={s.progressBar}>
                <View style={[s.progressFill, {width: `${progressPct}%`}]} />
              </View>
              <Text style={s.progressPct}>{progress.step}/{progress.total}</Text>
            </View>
          )}
        </View>
      )}

      {/* Scan log */}
      <View style={s.logCard}>
        <Text style={s.cardLabel}>SCAN LOG</Text>
        <ScrollView
          style={s.logScroll}
          ref={scrollRef}
          onContentSizeChange={() =>
            scrollRef.current?.scrollToEnd({animated: true})
          }>
          {log.length === 0 && (
            <Text style={s.logEmpty}>Waiting for scan...</Text>
          )}
          {log.map((entry, i) => (
            <Text
              key={i}
              style={[
                s.logLine,
                entry.type === 'error' && {color: C.red},
                entry.type === 'warn' && {color: C.amber},
                entry.type === 'success' && {color: C.green},
              ]}>
              [{entry.ts}] {entry.msg}
            </Text>
          ))}
        </ScrollView>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: C.bg, padding: 16},

  cardLabel: {
    color: C.textDim, fontSize: 11, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
  },

  // Vehicle
  vehicleCard: {
    backgroundColor: C.card, borderRadius: 12, padding: 20,
    marginBottom: 16, borderWidth: 1, borderColor: C.border,
  },
  vehicleText: {color: C.textBright, fontSize: 20, fontWeight: '700'},
  vehicleDetail: {color: C.textDim, fontSize: 14, marginTop: 4, lineHeight: 20},
  vinReadingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8,
  },
  vinReadingText: {color: C.accent, fontSize: 14, fontWeight: '600'},
  scanBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    padding: 16, alignItems: 'center', marginTop: 20,
    shadowColor: C.accent, shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  scanBtnText: {color: '#fff', fontSize: 16, fontWeight: '700'},
  errorBox: {
    backgroundColor: C.red + '18', borderRadius: 8, padding: 10,
    marginTop: 12, borderWidth: 1, borderColor: C.red + '44',
  },
  errorText: {color: C.red, fontSize: 13},

  // Progress
  progressCard: {
    backgroundColor: C.card, borderRadius: 12, padding: 24,
    marginBottom: 16, alignItems: 'center',
    borderWidth: 1, borderColor: C.border,
  },
  progressTitle: {
    color: C.textBright, fontSize: 18, fontWeight: '700', marginTop: 16,
  },

  // Stages
  stagesWrap: {width: '100%', marginTop: 20, gap: 6},
  stageRow: {
    flexDirection: 'row', alignItems: 'center',
    padding: 8, borderRadius: 8,
  },
  stageActive: {backgroundColor: C.accent + '12'},
  stageDone: {backgroundColor: C.green + '10'},
  stageIcon: {fontSize: 16, marginRight: 10, width: 24, textAlign: 'center'},
  stageLabel: {color: C.textDim, fontSize: 14},

  // Progress bar
  progressBarWrap: {width: '100%', marginTop: 16},
  progressBar: {
    width: '100%', height: 6, backgroundColor: C.border,
    borderRadius: 3, overflow: 'hidden',
  },
  progressFill: {height: '100%', backgroundColor: C.accent, borderRadius: 3},
  progressPct: {color: C.textDim, fontSize: 12, marginTop: 6, textAlign: 'center'},

  // Log
  logCard: {
    flex: 1, backgroundColor: C.bg, borderRadius: 12,
    borderWidth: 1, borderColor: C.border, padding: 12,
  },
  logScroll: {flex: 1},
  logEmpty: {color: C.textDim, fontSize: 13, fontStyle: 'italic'},
  logLine: {color: C.textDim, fontSize: 12, fontFamily: 'monospace', lineHeight: 20},
});
