/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet, StatusBar} from 'react-native';

// GNG Brand Palette
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

export default function HomeScreen({navigation}) {
  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />

      {/* Logo */}
      <View style={s.logoWrap}>
        <View style={s.iconBg}>
          <Text style={s.iconText}>L</Text>
        </View>
        <Text style={s.title}>LYLO <Text style={s.titleAccent}>Mechanic</Text></Text>
        <Text style={s.subtitle}>Know what's wrong before you walk in.</Text>
        <View style={s.taglineRow}>
          <View style={s.taglineDot} />
          <Text style={s.tagline}>Powered by OBDLink MX+</Text>
        </View>
      </View>

      {/* Main actions */}
      <View style={s.actionWrap}>
        <TouchableOpacity
          style={s.primaryBtn}
          activeOpacity={0.85}
          onPress={() => navigation.navigate('Connect')}>
          <Text style={s.primaryBtnIcon}>{'\u{1F50C}'}</Text>
          <Text style={s.primaryBtnText}>Connect to OBDLink</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={s.secondaryBtn}
          activeOpacity={0.85}
          onPress={() => navigation.navigate('Scan', {demo: true})}>
          <Text style={s.secondaryBtnIcon}>{'\u{1F9EA}'}</Text>
          <Text style={s.secondaryBtnText}>Try Demo Mode</Text>
        </TouchableOpacity>
      </View>

      {/* Feature pills */}
      <View style={s.featureRow}>
        <View style={s.pill}>
          <Text style={s.pillText}>{'\u{1F527}'} Diagnosis</Text>
        </View>
        <View style={s.pill}>
          <Text style={s.pillText}>{'\u{1F4B0}'} Cost Range</Text>
        </View>
        <View style={s.pill}>
          <Text style={s.pillText}>{'\u{1F5E3}'} ShopScript</Text>
        </View>
      </View>

      {/* Footer */}
      <View style={s.footer}>
        <Text style={s.footerBrand}>The Good Neighbor Guard</Text>
        <Text style={s.footerMotto}>Truth · Safety · We Got Your Back</Text>
        <Text style={s.version}>v1.0.0</Text>
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
    padding: 24,
  },

  // Logo
  logoWrap: {alignItems: 'center', marginBottom: 48},
  iconBg: {
    width: 80, height: 80, borderRadius: 20,
    backgroundColor: C.accent,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 20,
    shadowColor: C.accent, shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.4, shadowRadius: 16, elevation: 8,
  },
  iconText: {
    fontSize: 38, fontWeight: '900', color: C.bg,
  },
  title: {
    fontSize: 30, fontWeight: '800', color: C.textBright,
    letterSpacing: 0.5,
  },
  titleAccent: {color: C.accent},
  subtitle: {
    fontSize: 15, color: C.text, marginTop: 6,
  },
  taglineRow: {
    flexDirection: 'row', alignItems: 'center', marginTop: 8,
  },
  taglineDot: {
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: C.success, marginRight: 6,
  },
  tagline: {fontSize: 12, color: C.textDim},

  // Actions
  actionWrap: {width: '100%', gap: 12, marginBottom: 32},
  primaryBtn: {
    backgroundColor: C.accent,
    borderRadius: 12, padding: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    shadowColor: C.accent, shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  primaryBtnIcon: {fontSize: 18, marginRight: 10},
  primaryBtnText: {
    color: '#fff', fontSize: 17, fontWeight: '700',
  },
  secondaryBtn: {
    backgroundColor: C.panel,
    borderRadius: 12, padding: 14,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: C.border,
  },
  secondaryBtnIcon: {fontSize: 16, marginRight: 10},
  secondaryBtnText: {
    color: C.text, fontSize: 16, fontWeight: '600',
  },

  // Feature pills
  featureRow: {
    flexDirection: 'row', gap: 8, marginBottom: 48,
  },
  pill: {
    backgroundColor: C.panel,
    borderRadius: 20, paddingVertical: 6, paddingHorizontal: 12,
    borderWidth: 1, borderColor: C.border,
  },
  pillText: {color: C.textDim, fontSize: 12, fontWeight: '600'},

  // Footer
  footer: {
    position: 'absolute', bottom: 36,
    alignItems: 'center',
  },
  footerBrand: {color: C.gold, fontSize: 12, fontWeight: '700', letterSpacing: 0.5},
  footerMotto: {color: C.textDim, fontSize: 11, marginTop: 2},
  version: {color: C.border, fontSize: 10, marginTop: 4},
});
