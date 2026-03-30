import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, StatusBar} from 'react-native';

export default function HomeScreen({navigation}) {
  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0D1117" />

      {/* Logo */}
      <View style={s.logoWrap}>
        <View style={s.hexagon}>
          <Text style={s.hexText}>L</Text>
        </View>
        <Text style={s.title}>LYLO Mechanic</Text>
        <Text style={s.subtitle}>Powered by OBDLink MX+</Text>
      </View>

      {/* Main action */}
      <TouchableOpacity
        style={s.primaryBtn}
        onPress={() => navigation.navigate('Connect')}>
        <Text style={s.primaryBtnText}>Connect to OBDLink</Text>
      </TouchableOpacity>

      {/* Demo mode */}
      <TouchableOpacity
        style={s.secondaryBtn}
        onPress={() => navigation.navigate('Scan', {demo: true})}>
        <Text style={s.secondaryBtnText}>Demo Mode (No Adapter)</Text>
      </TouchableOpacity>

      {/* Footer */}
      <View style={s.footer}>
        <Text style={s.footerText}>
          The Good Neighbor Guard{'\n'}Truth . Safety . We Got Your Back
        </Text>
        <Text style={s.version}>v0.1.0</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D1117',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  logoWrap: {alignItems: 'center', marginBottom: 48},
  hexagon: {
    width: 80,
    height: 80,
    borderRadius: 16,
    backgroundColor: '#D4A843',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    transform: [{rotate: '45deg'}],
  },
  hexText: {
    fontSize: 36,
    fontWeight: '900',
    color: '#0D1117',
    transform: [{rotate: '-45deg'}],
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: '#E6EDF3',
    letterSpacing: 1,
  },
  subtitle: {
    fontSize: 14,
    color: '#8B949E',
    marginTop: 4,
  },
  primaryBtn: {
    backgroundColor: '#D4A843',
    paddingVertical: 16,
    paddingHorizontal: 48,
    borderRadius: 12,
    width: '100%',
    alignItems: 'center',
    marginBottom: 16,
  },
  primaryBtnText: {
    color: '#0D1117',
    fontSize: 18,
    fontWeight: '700',
  },
  secondaryBtn: {
    borderWidth: 1,
    borderColor: '#30363D',
    paddingVertical: 14,
    paddingHorizontal: 48,
    borderRadius: 12,
    width: '100%',
    alignItems: 'center',
  },
  secondaryBtnText: {
    color: '#8B949E',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    position: 'absolute',
    bottom: 32,
    alignItems: 'center',
  },
  footerText: {
    color: '#484F58',
    fontSize: 12,
    textAlign: 'center',
    lineHeight: 18,
  },
  version: {color: '#30363D', fontSize: 11, marginTop: 4},
});
