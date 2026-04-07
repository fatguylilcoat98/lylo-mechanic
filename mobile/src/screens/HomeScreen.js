/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, StatusBar} from 'react-native';
import {C} from '../constants/colors';

export default function HomeScreen({navigation}) {
  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />

      {/* Logo */}
      <View style={s.logoWrap}>
        <View style={s.iconOuter}>
          <View style={s.iconInner}>
            <View style={s.iconConnector}>
              <View style={s.pinRow}>
                {[0,1,2,3,4].map(i => <View key={i} style={s.pin} />)}
              </View>
              <View style={s.pinRow}>
                {[0,1,2,3,4].map(i => <View key={i} style={s.pin} />)}
              </View>
            </View>
            <View style={s.checkWrap}>
              <Text style={s.checkmark}>{'\u2713'}</Text>
            </View>
          </View>
        </View>

        <Text style={s.title}>LYLO Mechanic</Text>
        <Text style={s.subtitle}>Know what's wrong before you walk in.</Text>
        <View style={s.accentLine} />
      </View>

      {/* Main action */}
      <TouchableOpacity
        style={s.primaryBtn}
        activeOpacity={0.85}
        onPress={() => navigation.navigate('Connect')}>
        <Text style={s.primaryBtnText}>Connect to OBDLink</Text>
      </TouchableOpacity>

      {/* Demo mode */}
      <TouchableOpacity
        style={s.secondaryBtn}
        activeOpacity={0.7}
        onPress={() => navigation.navigate('Scan', {demo: true})}>
        <Text style={s.secondaryBtnText}>Demo Mode (No Adapter)</Text>
      </TouchableOpacity>

      {/* Feature pills */}
      <View style={s.featureRow}>
        <View style={s.pill}><Text style={s.pillText}>Diagnosis</Text></View>
        <View style={s.pill}><Text style={s.pillText}>Cost Range</Text></View>
        <View style={s.pill}><Text style={s.pillText}>ShopScript</Text></View>
      </View>

      {/* Bluetooth status hint */}
      <View style={s.statusRow}>
        <View style={s.statusDot} />
        <Text style={s.statusText}>Bluetooth Ready</Text>
      </View>

      {/* Footer */}
      <View style={s.footer}>
        <Text style={s.footerBrand}>The Good Neighbor Guard</Text>
        <Text style={s.footerTagline}>Truth · Safety · We Got Your Back</Text>
        <Text style={s.version}>v0.2.0</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: C.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 28,
  },

  // Logo
  logoWrap: {alignItems: 'center', marginBottom: 48},
  iconOuter: {
    width: 100, height: 100, borderRadius: 24,
    backgroundColor: C.card, borderWidth: 1.5, borderColor: C.accent,
    alignItems: 'center', justifyContent: 'center', marginBottom: 20,
    shadowColor: C.accent, shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 8,
  },
  iconInner: {alignItems: 'center', justifyContent: 'center'},
  iconConnector: {
    width: 56, height: 32, backgroundColor: C.accent,
    borderRadius: 6, paddingVertical: 4, paddingHorizontal: 6,
    justifyContent: 'center', gap: 3,
  },
  pinRow: {flexDirection: 'row', justifyContent: 'space-around'},
  pin: {width: 5, height: 5, borderRadius: 2.5, backgroundColor: C.bg},
  checkWrap: {
    position: 'absolute', bottom: -8, right: -12,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: C.green, alignItems: 'center', justifyContent: 'center',
  },
  checkmark: {color: '#fff', fontSize: 12, fontWeight: '900', marginTop: -1},

  title: {fontSize: 30, fontWeight: '800', color: C.textBright, letterSpacing: 0.5},
  subtitle: {fontSize: 15, color: C.text, marginTop: 6},
  accentLine: {
    width: 40, height: 3, backgroundColor: C.accent,
    borderRadius: 2, marginTop: 12,
  },

  // Buttons
  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10, backgroundColor: C.accent,
    paddingVertical: 16, paddingHorizontal: 32, borderRadius: 14,
    width: '100%', marginBottom: 14,
    shadowColor: C.accent, shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.35, shadowRadius: 12, elevation: 6,
  },
  primaryBtnText: {color: '#fff', fontSize: 17, fontWeight: '700', letterSpacing: 0.3},

  secondaryBtn: {
    borderWidth: 1, borderColor: C.border,
    paddingVertical: 14, paddingHorizontal: 32, borderRadius: 14,
    width: '100%', alignItems: 'center', backgroundColor: C.card,
    marginBottom: 24,
  },
  secondaryBtnText: {color: C.textDim, fontSize: 15, fontWeight: '600'},

  // Feature pills
  featureRow: {flexDirection: 'row', gap: 8, marginBottom: 32},
  pill: {
    backgroundColor: C.card, borderRadius: 20,
    paddingVertical: 6, paddingHorizontal: 14,
    borderWidth: 1, borderColor: C.border,
  },
  pillText: {color: C.textDim, fontSize: 12, fontWeight: '600'},

  // Status
  statusRow: {flexDirection: 'row', alignItems: 'center', gap: 8},
  statusDot: {width: 8, height: 8, borderRadius: 4, backgroundColor: C.green},
  statusText: {color: C.textDim, fontSize: 13, fontWeight: '500'},

  // Footer
  footer: {position: 'absolute', bottom: 36, alignItems: 'center'},
  footerBrand: {color: C.textMuted, fontSize: 13, fontWeight: '600', letterSpacing: 0.3},
  footerTagline: {color: C.textMuted, fontSize: 11, marginTop: 2},
  version: {color: C.border, fontSize: 11, marginTop: 6},
});
