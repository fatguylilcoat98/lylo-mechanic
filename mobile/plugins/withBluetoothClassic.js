/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Expo Config Plugin for react-native-bluetooth-classic
 *
 * Fixes:
 * 1. Adds Bluetooth Classic permissions to AndroidManifest
 * 2. Patches the outdated build.gradle in react-native-bluetooth-classic
 *    (it ships with Gradle 3.4.3 which breaks Expo 51+ builds)
 */

const {withAndroidManifest, withDangerousMod} = require('expo/config-plugins');
const fs = require('fs');
const path = require('path');

function withBluetoothClassicPermissions(config) {
  return withAndroidManifest(config, async (config) => {
    const manifest = config.modResults.manifest;

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

function withBluetoothClassicGradleFix(config) {
  return withDangerousMod(config, [
    'android',
    async (config) => {
      // Path to the library's build.gradle inside node_modules
      // EAS copies node_modules into the build, so we patch it post-install
      const projectRoot = config.modRequest.projectRoot;
      const gradlePath = path.join(
        projectRoot,
        'node_modules',
        'react-native-bluetooth-classic',
        'android',
        'build.gradle',
      );

      if (fs.existsSync(gradlePath)) {
        let gradle = fs.readFileSync(gradlePath, 'utf8');

        // Remove the entire buildscript block — Expo manages this at the root level
        gradle = gradle.replace(
          /buildscript\s*\{[\s\S]*?^}/m,
          '// buildscript removed by withBluetoothClassic plugin — managed by Expo',
        );

        // Remove 'apply plugin: com.android.library' if it causes duplicate
        // (Expo autolinking handles this)

        fs.writeFileSync(gradlePath, gradle, 'utf8');
        console.log('[withBluetoothClassic] Patched build.gradle — removed outdated buildscript');
      } else {
        console.warn('[withBluetoothClassic] build.gradle not found at:', gradlePath);
      }

      return config;
    },
  ]);
}

module.exports = function withBluetoothClassic(config) {
  config = withBluetoothClassicPermissions(config);
  config = withBluetoothClassicGradleFix(config);
  return config;
};
