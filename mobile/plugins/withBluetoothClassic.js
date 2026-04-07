/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Expo Config Plugin for react-native-bluetooth-classic
 *
 * This plugin ensures the native Android build includes the correct
 * Bluetooth permissions and settings for Classic Bluetooth (SPP/RFCOMM).
 */

const {withAndroidManifest} = require('expo/config-plugins');

function withBluetoothClassic(config) {
  return withAndroidManifest(config, async (config) => {
    const manifest = config.modResults.manifest;

    // Ensure permissions exist
    if (!manifest['uses-permission']) {
      manifest['uses-permission'] = [];
    }

    const perms = manifest['uses-permission'];
    const needed = [
      'android.permission.BLUETOOTH',
      'android.permission.BLUETOOTH_ADMIN',
      'android.permission.BLUETOOTH_SCAN',
      'android.permission.BLUETOOTH_CONNECT',
      'android.permission.ACCESS_FINE_LOCATION',
    ];

    for (const perm of needed) {
      if (!perms.find(p => p.$?.['android:name'] === perm)) {
        perms.push({$: {'android:name': perm}});
      }
    }

    return config;
  });
}

module.exports = withBluetoothClassic;
