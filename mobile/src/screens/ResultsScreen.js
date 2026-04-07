/**
 * The Good Neighbor Guard — LYLO Mechanic
 * Christopher Hughes · Sacramento, CA
 * AI Collaborators: Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 *
 * ResultsScreen — MVP 6-panel layout
 * Shows: what's wrong, urgency, cost, difficulty, ShopScript, red flags
 */

import React, {useState} from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Share, Clipboard,
} from 'react-native';

const URGENCY_STYLES = {
  green:  {bg: '#0D3D1B', border: '#238636', text: '#3FB950'},
  orange: {bg: '#3D2E00', border: '#9E6A03', text: '#D29922'},
  red:    {bg: '#3D1014', border: '#DA3633', text: '#F85149'},
};

const DIFFICULTY_COLORS = {
  Easy: '#3FB950',
  Medium: '#D29922',
  Hard: '#F85149',
};

function Card({title, icon, children}) {
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <Text style={s.cardIcon}>{icon}</Text>
        <Text style={s.cardTitle}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function ResultPanel({result, onCopyScript}) {
  const w = result.whats_wrong || {};
  const u = result.urgency || {};
  const c = result.cost || {};
  const d = result.difficulty || {};
  const uStyle = URGENCY_STYLES[u.color] || URGENCY_STYLES.orange;
  const dColor = DIFFICULTY_COLORS[d.level] || '#8B949E';

  return (
    <View>
      {/* 1. What's Likely Wrong */}
      <Card title="What's Likely Wrong" icon={"\u{1F527}"}>
        <Text style={s.summaryText}>{w.summary || ''}</Text>
        {w.likely_cause ? (
          <Text style={s.likelyCause}>
            Most likely: <Text style={s.likelyCauseValue}>{w.likely_cause}</Text>
          </Text>
        ) : null}
        {w.explanation ? (
          <Text style={s.explanation}>{w.explanation}</Text>
        ) : null}
        {w.other_possibilities && w.other_possibilities.length > 0 ? (
          <Text style={s.otherPossibilities}>
            Also possible: {w.other_possibilities.join(', ')}
          </Text>
        ) : null}
        {w.check_first && w.check_first.length > 0 ? (
          <View style={s.checkFirstBox}>
            {w.check_first.map((item, i) => (
              <Text key={i} style={s.checkFirstItem}>{'\u203A'} {item}</Text>
            ))}
          </View>
        ) : null}
      </Card>

      {/* 2. Urgency */}
      <Card title="Urgency" icon={"\u26A0\uFE0F"}>
        <View style={[s.urgencyBadge, {backgroundColor: uStyle.bg, borderColor: uStyle.border}]}>
          <Text style={[s.urgencyLevel, {color: uStyle.text}]}>
            {u.level || 'UNKNOWN'}
          </Text>
        </View>
        <Text style={s.urgencyMsg}>{u.message || ''}</Text>
      </Card>

      {/* 3. Estimated Cost */}
      <Card title="Estimated Cost" icon={"\u{1F4B0}"}>
        <View style={s.costGrid}>
          <View style={s.costItem}>
            <Text style={s.costLabel}>DIY</Text>
            <Text style={s.costValue}>{c.diy || 'N/A'}</Text>
          </View>
          <View style={s.costItem}>
            <Text style={s.costLabel}>SHOP</Text>
            <Text style={s.costValue}>{c.shop || 'N/A'}</Text>
          </View>
        </View>
        {c.dealer ? (
          <View style={s.costDealerRow}>
            <Text style={s.costLabel}>DEALER</Text>
            <Text style={[s.costValue, {color: '#D29922'}]}>{c.dealer}</Text>
          </View>
        ) : null}
        {c.note ? <Text style={s.costNote}>{c.note}</Text> : null}
      </Card>

      {/* 4. Fix Difficulty */}
      <Card title="Fix Difficulty" icon={"\u{1F6E0}"}>
        <View style={s.difficultyRow}>
          <Text style={[s.difficultyLevel, {color: dColor}]}>
            {d.level || 'Unknown'}
          </Text>
          <Text style={s.difficultyLabel}>{d.label || ''}</Text>
        </View>
      </Card>

      {/* 5. What To Say (ShopScript) */}
      <Card title="What To Say At The Shop" icon={"\u{1F5E3}"}>
        <View style={s.shopScriptBox}>
          <Text style={s.shopScriptText}>{result.shop_script || ''}</Text>
        </View>
        <TouchableOpacity style={s.copyBtn} onPress={() => onCopyScript(result.shop_script)}>
          <Text style={s.copyBtnText}>Copy to Clipboard</Text>
        </TouchableOpacity>
      </Card>

      {/* 6. Red Flags */}
      {result.red_flags && result.red_flags.length > 0 ? (
        <Card title="Red Flags" icon={"\u{1F6A9}"}>
          {result.red_flags.map((flag, i) => (
            <View key={i} style={s.redFlagItem}>
              <Text style={s.redFlagText}>{flag}</Text>
            </View>
          ))}
        </Card>
      ) : null}
    </View>
  );
}

export default function ResultsScreen({route, navigation}) {
  const data = route.params?.result;
  const [activeTab, setActiveTab] = useState(0);

  if (!data || !data.results || data.results.length === 0) {
    return (
      <View style={s.container}>
        <Text style={s.errorText}>No diagnosis result available.</Text>
        <TouchableOpacity style={s.backBtn} onPress={() => navigation.goBack()}>
          <Text style={s.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const results = data.results;
  const activeResult = results[activeTab] || results[0];

  const handleCopyScript = (script) => {
    if (!script) return;
    try {
      Clipboard.setString(script);
    } catch {
      // Fallback — some RN versions need different clipboard API
    }
  };

  const handleShare = async () => {
    const r = activeResult;
    const text = [
      `LYLO Mechanic — ${r.code || 'Diagnosis'}`,
      '',
      `What's wrong: ${r.whats_wrong?.summary || ''}`,
      `Urgency: ${r.urgency?.level || ''}`,
      `Cost (shop): ${r.cost?.shop || ''}`,
      `Difficulty: ${r.difficulty?.level || ''}`,
      '',
      'What to say:',
      r.shop_script || '',
      '',
      '— LYLO Mechanic by The Good Neighbor Guard',
    ].join('\n');

    try {
      await Share.share({message: text});
    } catch {
      // User cancelled
    }
  };

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerCode}>{activeResult.code || ''}</Text>
        {data.input ? (
          <Text style={s.headerInput}>You asked: "{data.input}"</Text>
        ) : null}
      </View>

      {/* Note banner for symptom matches */}
      {data.note ? (
        <View style={s.noteBanner}>
          <Text style={s.noteText}>{data.note}</Text>
        </View>
      ) : null}

      {/* Tabs for multiple results */}
      {results.length > 1 ? (
        <View style={s.tabs}>
          {results.map((r, i) => (
            <TouchableOpacity
              key={i}
              style={[s.tab, i === activeTab && s.tabActive]}
              onPress={() => setActiveTab(i)}>
              <Text style={[s.tabText, i === activeTab && s.tabTextActive]}>
                {r.code || `Result ${i + 1}`}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      ) : null}

      {/* Result panels */}
      <ResultPanel result={activeResult} onCopyScript={handleCopyScript} />

      {/* Actions */}
      <View style={s.actionRow}>
        <TouchableOpacity style={s.shareBtn} onPress={handleShare}>
          <Text style={s.shareBtnText}>Share Results</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={s.backBtn}
        onPress={() => navigation.popToTop()}>
        <Text style={s.backBtnText}>Check Another Issue</Text>
      </TouchableOpacity>

      <View style={{height: 40}} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#0D1117'},
  content: {padding: 16},
  errorText: {color: '#F85149', fontSize: 16, textAlign: 'center', marginTop: 40},

  // Header
  header: {alignItems: 'center', marginBottom: 16},
  headerCode: {
    fontSize: 32, fontWeight: '800', color: '#58A6FF',
    fontFamily: 'monospace',
  },
  headerInput: {color: '#8B949E', fontSize: 13, marginTop: 4},

  // Note
  noteBanner: {
    backgroundColor: 'rgba(88,166,255,0.1)', borderRadius: 8,
    padding: 12, marginBottom: 16, borderWidth: 1,
    borderColor: 'rgba(88,166,255,0.3)',
  },
  noteText: {color: '#58A6FF', fontSize: 13, textAlign: 'center'},

  // Tabs
  tabs: {flexDirection: 'row', gap: 8, marginBottom: 16, justifyContent: 'center'},
  tab: {
    backgroundColor: '#161B22', borderRadius: 8, paddingVertical: 8,
    paddingHorizontal: 16, borderWidth: 1, borderColor: '#21262D',
  },
  tabActive: {backgroundColor: '#58A6FF', borderColor: '#58A6FF'},
  tabText: {color: '#8B949E', fontSize: 14, fontWeight: '600'},
  tabTextActive: {color: '#000'},

  // Card
  card: {
    backgroundColor: '#161B22', borderRadius: 12, padding: 16,
    marginBottom: 12, borderWidth: 1, borderColor: '#21262D',
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', marginBottom: 12},
  cardIcon: {fontSize: 18, marginRight: 8},
  cardTitle: {
    fontSize: 13, fontWeight: '700', color: '#8B949E',
    textTransform: 'uppercase', letterSpacing: 1,
  },

  // What's wrong
  summaryText: {color: '#E6EDF3', fontSize: 15, fontWeight: '600', marginBottom: 8},
  likelyCause: {color: '#8B949E', fontSize: 14, marginBottom: 6},
  likelyCauseValue: {color: '#E6EDF3', fontWeight: '700'},
  explanation: {color: '#8B949E', fontSize: 14, lineHeight: 21, marginBottom: 8},
  otherPossibilities: {color: '#8B949E', fontSize: 13, marginBottom: 8, fontStyle: 'italic'},
  checkFirstBox: {
    backgroundColor: '#0D1117', borderRadius: 8, padding: 12, marginTop: 4,
  },
  checkFirstItem: {color: '#58A6FF', fontSize: 13, lineHeight: 22},

  // Urgency
  urgencyBadge: {
    borderRadius: 8, padding: 10, borderWidth: 1,
    alignSelf: 'flex-start', marginBottom: 8,
  },
  urgencyLevel: {fontSize: 16, fontWeight: '800'},
  urgencyMsg: {color: '#8B949E', fontSize: 14, lineHeight: 21},

  // Cost
  costGrid: {flexDirection: 'row', gap: 8, marginBottom: 8},
  costItem: {
    flex: 1, backgroundColor: '#0D1117', borderRadius: 8,
    padding: 12, alignItems: 'center',
  },
  costLabel: {
    fontSize: 12, color: '#8B949E', fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  costValue: {fontSize: 18, fontWeight: '700', color: '#3FB950', marginTop: 4},
  costDealerRow: {
    backgroundColor: '#0D1117', borderRadius: 8, padding: 12,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 8,
  },
  costNote: {color: '#484F58', fontSize: 12, marginTop: 4},

  // Difficulty
  difficultyRow: {flexDirection: 'row', alignItems: 'center', gap: 12},
  difficultyLevel: {fontSize: 20, fontWeight: '800'},
  difficultyLabel: {color: '#8B949E', fontSize: 14},

  // ShopScript
  shopScriptBox: {
    backgroundColor: '#0D1117', borderLeftWidth: 3, borderLeftColor: '#58A6FF',
    borderRadius: 8, padding: 16, marginBottom: 12,
  },
  shopScriptText: {
    color: '#E6EDF3', fontSize: 15, lineHeight: 24, fontStyle: 'italic',
  },
  copyBtn: {
    backgroundColor: '#21262D', borderRadius: 8, padding: 10,
    alignItems: 'center', borderWidth: 1, borderColor: '#30363D',
  },
  copyBtnText: {color: '#58A6FF', fontSize: 14, fontWeight: '600'},

  // Red flags
  redFlagItem: {
    backgroundColor: 'rgba(248,81,73,0.08)', borderLeftWidth: 3,
    borderLeftColor: '#F85149', borderRadius: 8, padding: 12,
    marginBottom: 8,
  },
  redFlagText: {color: '#E6EDF3', fontSize: 14, lineHeight: 21},

  // Actions
  actionRow: {marginTop: 8, marginBottom: 12},
  shareBtn: {
    backgroundColor: '#161B22', borderRadius: 10, padding: 14,
    alignItems: 'center', borderWidth: 1, borderColor: '#30363D',
  },
  shareBtnText: {color: '#E6EDF3', fontSize: 15, fontWeight: '600'},
  backBtn: {
    borderWidth: 1, borderColor: '#58A6FF', borderRadius: 10,
    padding: 14, alignItems: 'center',
  },
  backBtnText: {color: '#58A6FF', fontSize: 15, fontWeight: '600'},
});
