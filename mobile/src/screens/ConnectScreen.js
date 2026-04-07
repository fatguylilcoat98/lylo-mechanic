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

const C = {
  bg: '#0a0c0f',
  panel: '#0f1318',
  border: '#1e2a38',
  text: '#c8d6e2',
  textDim: '#4e6070',
  textBright: '#e8f4ff',
  accent: '#1a8fff',
  success: '#00c87a',
  warning: '#f0b429',
  danger: '#e03c3c',
  gold: '#c8a84b',
};

export default function ConnectScreen({navigation}) {
  const [phase, setPhase] = useState('idle'); // idle | scanning | connecting | ready
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [error, setError] = useState(null);
  const [initInfo, setInitInfo] = useState(null);
  const [btEnabled, setBtEnabled] = useState(true);

  useEffect(() => {
    (async () => {
      const granted = await BluetoothService.requestPermissions();
      if (!granted) {
        setError('Bluetooth permissions are required to connect to your OBDLink adapter.');
        return;
      }
      const enabled = await BluetoothService.isBluetoothEnabled();
      setBtEnabled(enabled);
      if (!enabled) {
        setError('Please enable Bluetooth in your device settings.');
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
      style={[s.deviceRow, item.isOBDLink && s.deviceRowOBD]}
      onPress={() => connectToDevice(item)}
      activeOpacity={0.7}
      disabled={phase === 'connecting'}>
      <View style={s.deviceInfo}>
        <Text style={s.deviceName}>{item.name}</Text>
        <Text style={s.deviceAddr}>
          {item.id?.substring(0, 17)}
          {item.rssi != null ? ` · ${item.rssi} dBm` : ''}
        </Text>
      </View>
      {item.isOBDLink && (
        <View style={s.obdBadge}>
          <Text style={s.obdBadgeText}>OBDLink</Text>
        </View>
      )}
      <Text style={s.chevron}>{'\u203A'}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={s.container}>
      {/* Bluetooth status */}
      <View style={s.statusRow}>
        <View style={[s.statusDot, {backgroundColor: btEnabled ? C.success : C.danger}]} />
        <Text style={s.statusText}>
          Bluetooth {btEnabled ? 'On' : 'Off'}
        </Text>
      </View>

      {/* Connected banner */}
      {phase === 'ready' && (
        <View style={s.connectedBanner}>
          <Text style={s.connectedIcon}>{'\u2705'}</Text>
          <View style={{flex: 1}}>
            <Text style={s.connectedText}>
              Connected to {selectedDevice?.name}
            </Text>
            {initInfo && (
              <Text style={s.protoText}>
                {initInfo.profile} · Protocol: {initInfo.protocol}
              </Text>
            )}
          </View>
        </View>
      )}

      {/* Error */}
      {error && (
        <View style={s.errorBanner}>
          <Text style={s.errorIcon}>{'\u26A0\uFE0F'}</Text>
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
                  <Text style={s.emptyIcon}>{'\u{1F50C}'}</Text>
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
              <View style={s.scanningRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.scanningText}>Scanning for BLE devices...</Text>
              </View>
            ) : phase === 'connecting' ? (
              <View style={s.scanningRow}>
                <ActivityIndicator size="small" color={C.accent} />
                <Text style={s.scanningText}>
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
          <View style={s.readyIconBg}>
            <Text style={s.readyIconText}>{'\u{1F527}'}</Text>
          </View>
          <Text style={s.readyTitle}>Adapter Ready</Text>
          <Text style={s.readySubtitle}>
            OBDLink MX+ is connected via BLE.{'\n'}Tap below to scan your vehicle.
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

  // Status
  statusRow: {
    flexDirection: 'row', alignItems: 'center',
    marginBottom: 16,
  },
  statusDot: {
    width: 8, height: 8, borderRadius: 4, marginRight: 8,
  },
  statusText: {color: C.textDim, fontSize: 13, fontWeight: '600'},

  // Section
  sectionTitle: {
    color: C.textBright, fontSize: 16, fontWeight: '700',
    marginBottom: 12, marginTop: 4,
  },
  list: {flex: 1},

  // Device rows
  deviceRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.panel, borderRadius: 12,
    padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: C.border,
  },
  deviceRowOBD: {borderColor: C.accent, borderLeftWidth: 3},
  deviceInfo: {flex: 1},
  deviceName: {color: C.textBright, fontSize: 15, fontWeight: '600'},
  deviceAddr: {color: C.textDim, fontSize: 12, marginTop: 2},
  obdBadge: {
    backgroundColor: C.accent + '22', borderRadius: 6,
    paddingHorizontal: 8, paddingVertical: 3, marginRight: 8,
  },
  obdBadgeText: {color: C.accent, fontSize: 11, fontWeight: '700'},
  chevron: {color: C.textDim, fontSize: 22, fontWeight: '300'},

  // Empty
  emptyWrap: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  emptyIcon: {fontSize: 40, marginBottom: 16},
  emptyText: {
    color: C.textDim, fontSize: 14, textAlign: 'center', lineHeight: 22,
  },

  // Actions
  actions: {paddingVertical: 16},
  scanBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    padding: 16, alignItems: 'center',
    shadowColor: C.accent, shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  scanBtnText: {color: '#fff', fontSize: 16, fontWeight: '700'},
  scanningRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  scanningText: {color: C.accent, fontSize: 15, marginLeft: 10},

  // Connected
  connectedBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.success + '18', borderRadius: 12, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: C.success + '44',
  },
  connectedIcon: {fontSize: 20, marginRight: 12},
  connectedText: {color: C.success, fontSize: 15, fontWeight: '700'},
  protoText: {color: C.textDim, fontSize: 12, marginTop: 2},

  // Error
  errorBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.danger + '18', borderRadius: 12, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: C.danger + '44',
  },
  errorIcon: {fontSize: 18, marginRight: 10},
  errorText: {color: C.danger, fontSize: 14, flex: 1},

  // Ready
  readyWrap: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  readyIconBg: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: C.success + '22', alignItems: 'center',
    justifyContent: 'center', marginBottom: 20,
  },
  readyIconText: {fontSize: 32},
  readyTitle: {
    color: C.success, fontSize: 24, fontWeight: '800', marginBottom: 8,
  },
  readySubtitle: {
    color: C.textDim, fontSize: 14, textAlign: 'center',
    lineHeight: 22, marginBottom: 32,
  },
  goBtn: {
    backgroundColor: C.accent, paddingVertical: 16, paddingHorizontal: 48,
    borderRadius: 12, width: '100%', alignItems: 'center',
    shadowColor: C.accent, shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  goBtnText: {color: '#fff', fontSize: 18, fontWeight: '700'},
});
