import React, {useState, useEffect, useCallback} from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  ActivityIndicator, Alert,
} from 'react-native';
import BluetoothService from '../services/BluetoothService';
import OBDService from '../services/OBDService';

export default function ConnectScreen({navigation}) {
  const [phase, setPhase] = useState('idle'); // idle | scanning | connecting | ready
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [error, setError] = useState(null);
  const [initInfo, setInitInfo] = useState(null);

  // Load paired devices on mount
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
        return;
      }
      // Show paired devices immediately
      const paired = await BluetoothService.getPairedDevices();
      setDevices(paired);
    })();
  }, []);

  const startDiscovery = useCallback(async () => {
    setPhase('scanning');
    setError(null);
    const discovered = await BluetoothService.discoverDevices(device => {
      setDevices(prev => {
        if (prev.find(d => d.address === device.address)) return prev;
        return [...prev, device];
      });
    });
    setPhase('idle');
  }, []);

  const connectToDevice = useCallback(async (device) => {
    setPhase('connecting');
    setSelectedDevice(device);
    setError(null);

    try {
      await BluetoothService.connect(device.address);

      // Initialize ELM327
      const info = await OBDService.initialize();
      setInitInfo(info);
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
          {item.isOBDLink ? '* ' : ''}{item.name}
        </Text>
        <Text style={s.deviceAddr}>{item.address}</Text>
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
      {/* Status banner */}
      {phase === 'ready' && (
        <View style={s.connectedBanner}>
          <Text style={s.connectedText}>
            Connected to {selectedDevice?.name}
          </Text>
          {initInfo && (
            <Text style={s.protoText}>Protocol: {initInfo.protocol}</Text>
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
            {devices.length > 0 ? 'Available Devices' : 'No devices found'}
          </Text>

          <FlatList
            data={devices}
            keyExtractor={item => item.address}
            renderItem={renderDevice}
            style={s.list}
            ListEmptyComponent={
              <Text style={s.emptyText}>
                Pair your OBDLink MX+ in Android Bluetooth settings first,
                then it will appear here.
              </Text>
            }
          />

          {/* Actions */}
          <View style={s.actions}>
            {phase === 'scanning' ? (
              <View style={s.scanningRow}>
                <ActivityIndicator color="#D4A843" />
                <Text style={s.scanningText}>Scanning...</Text>
              </View>
            ) : phase === 'connecting' ? (
              <View style={s.scanningRow}>
                <ActivityIndicator color="#D4A843" />
                <Text style={s.scanningText}>
                  Connecting to {selectedDevice?.name}...
                </Text>
              </View>
            ) : (
              <TouchableOpacity style={s.scanBtn} onPress={startDiscovery}>
                <Text style={s.scanBtnText}>Scan for New Devices</Text>
              </TouchableOpacity>
            )}
          </View>
        </>
      )}

      {/* Connected — proceed button */}
      {phase === 'ready' && (
        <View style={s.readyWrap}>
          <Text style={s.readyIcon}>*</Text>
          <Text style={s.readyTitle}>Adapter Ready</Text>
          <Text style={s.readySubtitle}>
            OBDLink MX+ is connected and initialized.
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
  readyIcon: {fontSize: 48, marginBottom: 16},
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
