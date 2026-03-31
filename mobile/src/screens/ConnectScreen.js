import React, {useState, useEffect, useCallback} from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  ActivityIndicator,
} from 'react-native';
import BluetoothService from '../services/BluetoothService';
import OBDService from '../services/OBDService';

export default function ConnectScreen({navigation}) {
  const [phase, setPhase] = useState('idle'); // idle | scanning | connecting | ready
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [error, setError] = useState(null);
  const [initInfo, setInitInfo] = useState(null);

  useEffect(() => {
    (async () => {
      const granted = await BluetoothService.requestPermissions();
      if (!granted) {
        setError('Bluetooth permissions are required to connect to OBDLink.');
        return;
      }
      const enabled = await BluetoothService.isBluetoothEnabled();
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
        // Sort OBDLink devices to top
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

      // Initialize ELM327 over BLE
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
      style={[s.deviceRow, item.isOBDLink && s.deviceRowHighlight]}
      onPress={() => connectToDevice(item)}
      disabled={phase === 'connecting'}>
      <View style={s.deviceInfo}>
        <Text style={s.deviceName}>
          {item.name}
        </Text>
        <Text style={s.deviceAddr}>
          {item.id?.substring(0, 17)} | RSSI: {item.rssi ?? '?'} dBm
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
      {/* Connected banner */}
      {phase === 'ready' && (
        <View style={s.connectedBanner}>
          <Text style={s.connectedText}>
            Connected to {selectedDevice?.name}
          </Text>
          {initInfo && (
            <>
              <Text style={s.protoText}>Profile: {initInfo.profile}</Text>
              <Text style={s.protoText}>Protocol: {initInfo.protocol}</Text>
            </>
          )}
        </View>
      )}

      {error && (
        <View style={s.errorBanner}>
          <Text style={s.errorText}>{error}</Text>
        </View>
      )}

      {/* Device list */}
      {phase !== 'ready' && (
        <>
          <Text style={s.sectionTitle}>
            {devices.length > 0
              ? `Found ${devices.length} device${devices.length > 1 ? 's' : ''}`
              : 'Tap Scan to find your OBDLink'}
          </Text>

          <FlatList
            data={devices}
            keyExtractor={item => item.id}
            renderItem={renderDevice}
            style={s.list}
            ListEmptyComponent={
              phase !== 'scanning' ? (
                <Text style={s.emptyText}>
                  Turn on your OBDLink MX+ adapter (plug it into the OBD port
                  under your dash), then tap "Scan for Devices" below.
                </Text>
              ) : null
            }
          />

          {/* Actions */}
          <View style={s.actions}>
            {phase === 'scanning' ? (
              <View style={s.scanningRow}>
                <ActivityIndicator color="#D4A843" />
                <Text style={s.scanningText}>Scanning for BLE devices...</Text>
              </View>
            ) : phase === 'connecting' ? (
              <View style={s.scanningRow}>
                <ActivityIndicator color="#D4A843" />
                <Text style={s.scanningText}>
                  Connecting to {selectedDevice?.name}...
                </Text>
              </View>
            ) : (
              <TouchableOpacity style={s.scanBtn} onPress={startScan}>
                <Text style={s.scanBtnText}>Scan for Devices</Text>
              </TouchableOpacity>
            )}
          </View>
        </>
      )}

      {/* Connected — proceed */}
      {phase === 'ready' && (
        <View style={s.readyWrap}>
          <Text style={s.readyTitle}>Adapter Ready</Text>
          <Text style={s.readySubtitle}>
            OBDLink MX+ is connected via BLE.
            {'\n'}Tap below to scan your vehicle.
          </Text>
          <TouchableOpacity style={s.goBtn} onPress={proceed}>
            <Text style={s.goBtnText}>Start Vehicle Scan</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#0D1117', padding: 16},
  sectionTitle: {
    color: '#E6EDF3', fontSize: 16, fontWeight: '700',
    marginBottom: 12, marginTop: 8,
  },
  list: {flex: 1},
  deviceRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#161B22', borderRadius: 10,
    padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: '#21262D',
  },
  deviceRowHighlight: {borderColor: '#D4A843'},
  deviceInfo: {flex: 1},
  deviceName: {color: '#E6EDF3', fontSize: 15, fontWeight: '600'},
  deviceAddr: {color: '#8B949E', fontSize: 12, marginTop: 2},
  obdBadge: {
    backgroundColor: '#D4A84322', borderRadius: 6,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  obdBadgeText: {color: '#D4A843', fontSize: 11, fontWeight: '700'},
  emptyText: {
    color: '#484F58', fontSize: 14, textAlign: 'center',
    marginTop: 32, lineHeight: 22, paddingHorizontal: 16,
  },
  actions: {paddingVertical: 16},
  scanBtn: {
    backgroundColor: '#21262D', borderRadius: 10,
    padding: 14, alignItems: 'center',
    borderWidth: 1, borderColor: '#30363D',
  },
  scanBtnText: {color: '#E6EDF3', fontSize: 15, fontWeight: '600'},
  scanningRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    padding: 14,
  },
  scanningText: {color: '#D4A843', fontSize: 15, marginLeft: 10},
  connectedBanner: {
    backgroundColor: '#0D3D1B', borderRadius: 10, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: '#238636',
  },
  connectedText: {color: '#3FB950', fontSize: 15, fontWeight: '700'},
  protoText: {color: '#8B949E', fontSize: 12, marginTop: 4},
  errorBanner: {
    backgroundColor: '#3D1014', borderRadius: 10, padding: 14,
    marginBottom: 12, borderWidth: 1, borderColor: '#DA3633',
  },
  errorText: {color: '#F85149', fontSize: 14},
  readyWrap: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  readyTitle: {
    color: '#3FB950', fontSize: 22, fontWeight: '800', marginBottom: 8,
  },
  readySubtitle: {
    color: '#8B949E', fontSize: 14, textAlign: 'center',
    lineHeight: 22, marginBottom: 32,
  },
  goBtn: {
    backgroundColor: '#D4A843', paddingVertical: 16, paddingHorizontal: 48,
    borderRadius: 12, width: '100%', alignItems: 'center',
  },
  goBtnText: {color: '#0D1117', fontSize: 18, fontWeight: '700'},
});
