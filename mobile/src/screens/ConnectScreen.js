/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  ActivityIndicator, Alert,
} from 'react-native';
import BluetoothService from '../services/BluetoothService';
import OBDService from '../services/OBDService';
import {C} from '../constants/colors';

export default function ConnectScreen({navigation}) {
  const [phase, setPhase] = useState('idle');
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [error, setError] = useState(null);
  const [initInfo, setInitInfo] = useState(null);
  const [btEnabled, setBtEnabled] = useState(true);

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

  const startScan = useCallback(async () => {
    setPhase('scanning');
    setError(null);
    setDevices([]);

    await BluetoothService.scanForDevices(device => {
      setDevices(prev => {
        if (prev.find(d => d.id === device.id)) return prev;
        const next = [...prev, device];
        next.sort((a, b) => (b.isOBDLink ? 1 : 0) - (a.isOBDLink ? 1 : 0));
        return next;
      });
    });

    setPhase('idle');
  }, []);

  const connectToDevice = useCallback(async (device) => {
    setPhase('connecting');
    setSelectedDevice(device);
    setError(null);

    try {
      const connInfo = await BluetoothService.connect(device.id);
      const info = await OBDService.initialize();
      setInitInfo({...info, profile: connInfo.profile});
      setPhase('ready');
    } catch (err) {
      setError(`Connection failed: ${err.message}`);
      setPhase('idle');
      setSelectedDevice(null);
    }
  }, []);

  const proceed = useCallback(() => {
    navigation.navigate('Scan', {demo: false});
  }, [navigation]);

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
          {item.id?.substring(0, 17)}{item.rssi != null ? ` \u00B7 ${item.rssi} dBm` : ''}
        </Text>
      </View>
      {item.isOBDLink && (
        <View style={s.obdBadge}>
          <Text style={s.obdBadgeText}>OBDLink</Text>
        </View>
      )}
    </TouchableOpacity>
  );

  return (
    <View style={s.container}>
      {/* Bluetooth status */}
      <View style={s.statusRow}>
        <View style={[s.statusDot, {backgroundColor: btEnabled ? C.green : C.red}]} />
        <Text style={s.statusText}>
          Bluetooth {btEnabled ? 'On' : 'Off'}
        </Text>
      </View>

      {/* Connected banner */}
      {phase === 'ready' && (
        <View style={s.connectedBanner}>
          <View style={s.connectedDot} />
          <View style={{flex: 1}}>
            <Text style={s.connectedText}>
              Connected to {selectedDevice?.name}
            </Text>
            {initInfo && (
              <Text style={s.protoText}>
                {initInfo.profile} \u00B7 Protocol: {initInfo.protocol}
              </Text>
            )}
          </View>
        </View>
      )}

      {/* Error */}
      {error && (
        <View style={s.errorBanner}>
          <Text style={s.errorIcon}>!</Text>
          <Text style={s.errorText}>{error}</Text>
        </View>
      )}

      {/* Device list */}
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
            keyExtractor={item => item.id}
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

          {/* Actions */}
          <View style={s.actions}>
            {phase === 'scanning' ? (
              <View style={s.loadingRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.loadingText}>Scanning for BLE devices...</Text>
              </View>
            ) : phase === 'connecting' ? (
              <View style={s.loadingRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.loadingText}>
                  Connecting to {selectedDevice?.name}...
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

      {/* Connected — proceed */}
      {phase === 'ready' && (
        <View style={s.readyWrap}>
          <View style={s.readyIcon}>
            <Text style={s.readyCheckmark}>{'\u2713'}</Text>
          </View>
          <Text style={s.readyTitle}>Adapter Ready</Text>
          <Text style={s.readySubtitle}>
            OBDLink MX+ connected via BLE.{'\n'}Tap below to scan your vehicle.
          </Text>
          <TouchableOpacity style={s.goBtn} onPress={proceed} activeOpacity={0.85}>
            <Text style={s.goBtnText}>Start Vehicle Scan</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: C.bg, padding: 16},

  // BT Status
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

  // Empty state
  emptyWrap: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32},
  emptyIcon: {color: C.border, fontSize: 40, marginBottom: 12},
  emptyText: {
    color: C.textDim, fontSize: 14, textAlign: 'center', lineHeight: 22,
  },

  // Actions
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
    padding: 16, gap: 10,
  },
  loadingText: {color: C.accent, fontSize: 15, fontWeight: '600'},

  // Connected banner
  connectedBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.greenDim, borderRadius: 12, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: C.green, gap: 12,
  },
  connectedDot: {width: 12, height: 12, borderRadius: 6, backgroundColor: C.green},
  connectedText: {color: C.green, fontSize: 15, fontWeight: '700'},
  protoText: {color: C.textDim, fontSize: 12, marginTop: 3},

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

  // Ready state
  readyWrap: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  readyIcon: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: C.greenDim, borderWidth: 2, borderColor: C.green,
    alignItems: 'center', justifyContent: 'center', marginBottom: 16,
  },
  readyCheckmark: {color: C.green, fontSize: 28, fontWeight: '900'},
  readyTitle: {color: C.green, fontSize: 24, fontWeight: '800', marginBottom: 8},
  readySubtitle: {
    color: C.textDim, fontSize: 14, textAlign: 'center',
    lineHeight: 22, marginBottom: 32,
  },
  goBtn: {
    backgroundColor: C.accent, paddingVertical: 16, paddingHorizontal: 48,
    borderRadius: 14, width: '100%', alignItems: 'center',
    shadowColor: C.accent, shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3, shadowRadius: 12, elevation: 6,
  },
  goBtnText: {color: '#fff', fontSize: 18, fontWeight: '700'},
});
