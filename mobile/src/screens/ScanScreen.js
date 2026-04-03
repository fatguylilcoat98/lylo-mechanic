import React, {useState, useEffect, useRef} from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator,
  TouchableOpacity, Alert,
} from 'react-native';
import OBDService from '../services/OBDService';
import ApiClient from '../services/ApiClient';

// Embedded demo result — works offline with zero Bluetooth and zero API
const DEMO_RESULT = {
  vehicle: {year: 2017, make: 'Honda', model: 'Civic', engine: '1.5L Turbo'},
  diagnosis: {
    headline: 'Catalytic Converter Efficiency Below Threshold',
    confidence: 82,
    severity: 'moderate',
    summary: 'Code P0420 indicates the catalytic converter on Bank 1 is not operating '
      + 'at expected efficiency. This is commonly triggered by a failing catalytic converter, '
      + 'but can also be caused by an exhaust leak, faulty O2 sensor, or engine misfire.',
    dtcs: [{code: 'P0420', description: 'Catalyst System Efficiency Below Threshold (Bank 1)'}],
    possible_causes: [
      'Worn or failing catalytic converter',
      'Faulty downstream O2 sensor (Bank 1, Sensor 2)',
      'Exhaust leak before or after catalytic converter',
      'Engine misfire causing unburnt fuel to damage catalyst',
    ],
    recommended_actions: [
      'Inspect exhaust system for leaks — check gaskets, flex pipe, and welds',
      'Test downstream O2 sensor response time and voltage range',
      'Check for engine misfires (Mode $06 data) that could damage catalyst',
      'If converter is confirmed failed, replacement cost is typically $800-$1,500 (parts + labor)',
    ],
    safety_note: 'Safe to drive short-term. Do not ignore — a failed catalytic converter '
      + 'will cause emissions test failure and may damage O2 sensors over time.',
    diy_difficulty: 'Intermediate (sensor testing) to Advanced (converter replacement)',
  },
};

const DEMO_VEHICLE = {
  year: 2017,
  make: 'Honda',
  model: 'Civic',
  engine: '1.5L Turbo',
  odometer: 87000,
};

export default function ScanScreen({route, navigation}) {
  const isDemo = route.params?.demo ?? false;
  const [phase, setPhase] = useState('vehicle'); // vehicle | scanning | sending | done
  const [progress, setProgress] = useState({step: 0, total: 0, msg: ''});
  const [log, setLog] = useState([]);
  const [scanData, setScanData] = useState(null);
  const [vehicle, setVehicle] = useState(DEMO_VEHICLE);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  const addLog = (msg, type = 'info') => {
    const ts = new Date().toLocaleTimeString('en-US', {
      hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    setLog(prev => [...prev, {ts, msg, type}]);
  };

  const startScan = async () => {
    setPhase('scanning');
    setError(null);

    if (isDemo) {
      // Demo mode — works offline with zero Bluetooth and zero API
      addLog('Demo mode — P0420 catalytic converter scenario', 'info');
      setPhase('sending');
      addLog('Running diagnostic pipeline...', 'info');

      // Try backend first, fall back to embedded mock data
      let result;
      try {
        const alive = await ApiClient.ping();
        if (alive) {
          addLog('Backend connected — running live scenario...', 'info');
          result = await ApiClient.diagnoseScenario('p0420_not_what_it_seems');
        } else {
          addLog('Backend offline — using embedded demo data', 'info');
          result = DEMO_RESULT;
        }
      } catch (err) {
        addLog('Backend unavailable — using embedded demo data', 'info');
        result = DEMO_RESULT;
      }

      // Brief delay so user can read the log
      await new Promise(r => setTimeout(r, 800));
      addLog('Diagnosis complete.', 'success');
      navigation.replace('Results', {result});
      return;
    }

    // Live scan
    try {
      addLog('Starting OBD-II full vehicle scan...', 'info');

      const data = await OBDService.fullScan((step, total, msg) => {
        setProgress({step, total, msg});
        addLog(msg, 'info');
      });

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

      // Send to backend
      setPhase('sending');
      addLog('Sending data to LYLO diagnostic engine...', 'info');

      const result = await ApiClient.diagnose(data, vehicle);
      addLog('Diagnosis complete.', 'success');

      navigation.replace('Results', {result});
    } catch (err) {
      setError(`Scan failed: ${err.message}`);
      addLog(`Error: ${err.message}`, 'error');
      setPhase('vehicle');
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
          <Text style={s.cardTitle}>Vehicle</Text>
          <Text style={s.vehicleText}>
            {vehicle.year} {vehicle.make} {vehicle.model}
          </Text>
          <Text style={s.vehicleDetail}>
            {vehicle.engine} | {vehicle.odometer.toLocaleString()} mi
          </Text>

          {error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          <TouchableOpacity style={s.scanBtn} onPress={startScan}>
            <Text style={s.scanBtnText}>
              {isDemo ? 'Run Demo Scan' : 'Scan Vehicle'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Progress */}
      {(phase === 'scanning' || phase === 'sending') && (
        <View style={s.progressCard}>
          <ActivityIndicator size="large" color="#D4A843" />
          <Text style={s.progressTitle}>
            {phase === 'scanning' ? 'Scanning Vehicle...' : 'Analyzing...'}
          </Text>
          {phase === 'scanning' && progress.total > 0 && (
            <>
              <Text style={s.progressMsg}>{progress.msg}</Text>
              <View style={s.progressBar}>
                <View style={[s.progressFill, {width: `${progressPct}%`}]} />
              </View>
              <Text style={s.progressPct}>
                {progress.step}/{progress.total}
              </Text>
            </>
          )}
          {phase === 'sending' && (
            <Text style={s.progressMsg}>
              Running 12-layer diagnostic pipeline...
            </Text>
          )}
        </View>
      )}

      {/* Scan log */}
      <View style={s.logCard}>
        <Text style={s.logTitle}>Scan Log</Text>
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
                entry.type === 'error' && s.logError,
                entry.type === 'warn' && s.logWarn,
                entry.type === 'success' && s.logSuccess,
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
  container: {flex: 1, backgroundColor: '#0D1117', padding: 16},
  vehicleCard: {
    backgroundColor: '#161B22', borderRadius: 12, padding: 20,
    marginBottom: 16, borderWidth: 1, borderColor: '#21262D',
  },
  cardTitle: {
    color: '#8B949E', fontSize: 12, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
  },
  vehicleText: {color: '#E6EDF3', fontSize: 20, fontWeight: '700'},
  vehicleDetail: {color: '#8B949E', fontSize: 14, marginTop: 4},
  scanBtn: {
    backgroundColor: '#D4A843', borderRadius: 10,
    padding: 14, alignItems: 'center', marginTop: 20,
  },
  scanBtnText: {color: '#0D1117', fontSize: 16, fontWeight: '700'},
  errorBox: {
    backgroundColor: '#3D1014', borderRadius: 8, padding: 10,
    marginTop: 12, borderWidth: 1, borderColor: '#DA3633',
  },
  errorText: {color: '#F85149', fontSize: 13},
  progressCard: {
    backgroundColor: '#161B22', borderRadius: 12, padding: 24,
    marginBottom: 16, alignItems: 'center',
    borderWidth: 1, borderColor: '#21262D',
  },
  progressTitle: {
    color: '#E6EDF3', fontSize: 18, fontWeight: '700', marginTop: 16,
  },
  progressMsg: {color: '#8B949E', fontSize: 13, marginTop: 8},
  progressBar: {
    width: '100%', height: 6, backgroundColor: '#21262D',
    borderRadius: 3, marginTop: 12, overflow: 'hidden',
  },
  progressFill: {height: '100%', backgroundColor: '#D4A843', borderRadius: 3},
  progressPct: {color: '#484F58', fontSize: 12, marginTop: 6},
  logCard: {
    flex: 1, backgroundColor: '#0D1117', borderRadius: 12,
    borderWidth: 1, borderColor: '#21262D', padding: 12,
  },
  logTitle: {
    color: '#8B949E', fontSize: 12, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
  },
  logScroll: {flex: 1},
  logEmpty: {color: '#484F58', fontSize: 13, fontStyle: 'italic'},
  logLine: {color: '#8B949E', fontSize: 12, fontFamily: 'monospace', lineHeight: 20},
  logError: {color: '#F85149'},
  logWarn: {color: '#D29922'},
  logSuccess: {color: '#3FB950'},
});
