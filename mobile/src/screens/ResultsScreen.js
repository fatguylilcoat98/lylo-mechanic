/*
 * LYLO Mechanic — The Good Neighbor Guard
 * Christopher Hughes · Sacramento, CA
 * Built with Claude · GPT · Gemini · Groq
 * Truth · Safety · We Got Your Back
 */

import React, {useState} from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Share, Clipboard,
} from 'react-native';
import {C} from '../constants/colors';


const URGENCY_STYLES = {
  green:  {bg: C.green + '18', border: C.green + '44', text: C.green},
  orange: {bg: C.amber + '18', border: C.amber + '44', text: C.amber},
  red:    {bg: C.red + '18', border: C.red + '44', text: C.red},
};

const DIFFICULTY_COLORS = {
  Easy: C.green,
  Medium: C.amber,
  Hard: C.red,
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
  const dColor = DIFFICULTY_COLORS[d.level] || C.textDim;

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
            <Text style={[s.costValue, {color: C.amber}]}>{c.dealer}</Text>
          </View>
        ) : null}
        {c.note ? <Text style={s.costNote}>{c.note}</Text> : null}
      </Card>

      {/* 4. Fix Difficulty */}
      <Card title="Fix Difficulty" icon={"\u{1F6E0}"}>
        <View style={s.difficultyRow}>
          <View style={[s.difficultyBadge, {backgroundColor: dColor + '22'}]}>
            <Text style={[s.difficultyLevel, {color: dColor}]}>
              {d.level || 'Unknown'}
            </Text>
          </View>
          <Text style={s.difficultyLabel}>{d.label || ''}</Text>
        </View>
      </Card>

      {/* 5. What To Say (ShopScript) */}
      <Card title="What To Say At The Shop" icon={"\u{1F5E3}"}>
        <View style={s.shopScriptBox}>
          <Text style={s.shopScriptText}>{result.shop_script || ''}</Text>
        </View>
        <TouchableOpacity
          style={s.copyBtn}
          onPress={() => onCopyScript(result.shop_script)}
          activeOpacity={0.85}>
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
  const [copied, setCopied] = useState(false);

  if (!data || !data.results || data.results.length === 0) {
    return (
      <View style={[s.container, {justifyContent: 'center', alignItems: 'center'}]}>
        <Text style={{color: C.red, fontSize: 16}}>No diagnosis result available.</Text>
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
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
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
      'What to say at the shop:',
      r.shop_script || '',
      '',
      '— LYLO Mechanic by The Good Neighbor Guard',
      'We Got Your Back',
    ].join('\n');

    try {
      await Share.share({message: text});
    } catch {}
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

      {/* Note banner */}
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

      {/* Copied toast */}
      {copied && (
        <View style={s.copiedToast}>
          <Text style={s.copiedText}>{'\u2705'} Copied to clipboard</Text>
        </View>
      )}

      {/* Actions */}
      <View style={s.actionRow}>
        <TouchableOpacity style={s.shareBtn} onPress={handleShare} activeOpacity={0.85}>
          <Text style={s.shareBtnText}>{'\u{1F4E4}'} Share Results</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={s.backBtn}
        onPress={() => navigation.popToTop()}
        activeOpacity={0.85}>
        <Text style={s.backBtnText}>Check Another Issue</Text>
      </TouchableOpacity>

      {/* Footer */}
      <View style={s.footer}>
        <Text style={s.footerBrand}>The Good Neighbor Guard</Text>
        <Text style={s.footerNote}>Not a substitute for professional diagnosis.</Text>
      </View>

      <View style={{height: 40}} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: C.bg},
  content: {padding: 16},

  // Header
  header: {alignItems: 'center', marginBottom: 16, paddingTop: 8},
  headerCode: {
    fontSize: 32, fontWeight: '800', color: C.accent,
    fontFamily: 'monospace',
  },
  headerInput: {color: C.textDim, fontSize: 13, marginTop: 4},

  // Note
  noteBanner: {
    backgroundColor: C.accent + '15', borderRadius: 10,
    padding: 12, marginBottom: 16, borderWidth: 1,
    borderColor: C.accent + '33',
  },
  noteText: {color: C.accent, fontSize: 13, textAlign: 'center'},

  // Tabs
  tabs: {flexDirection: 'row', gap: 8, marginBottom: 16, justifyContent: 'center'},
  tab: {
    backgroundColor: C.card, borderRadius: 8, paddingVertical: 8,
    paddingHorizontal: 16, borderWidth: 1, borderColor: C.border,
  },
  tabActive: {backgroundColor: C.accent, borderColor: C.accent},
  tabText: {color: C.textDim, fontSize: 14, fontWeight: '600'},
  tabTextActive: {color: '#fff'},

  // Card
  card: {
    backgroundColor: C.card, borderRadius: 12, padding: 16,
    marginBottom: 12, borderWidth: 1, borderColor: C.border,
  },
  cardHeader: {flexDirection: 'row', alignItems: 'center', marginBottom: 12},
  cardIcon: {fontSize: 18, marginRight: 8},
  cardTitle: {
    fontSize: 13, fontWeight: '700', color: C.textDim,
    textTransform: 'uppercase', letterSpacing: 1,
  },

  // What's wrong
  summaryText: {color: C.textBright, fontSize: 15, fontWeight: '600', marginBottom: 8},
  likelyCause: {color: C.textDim, fontSize: 14, marginBottom: 6},
  likelyCauseValue: {color: C.textBright, fontWeight: '700'},
  explanation: {color: C.text, fontSize: 14, lineHeight: 21, marginBottom: 8},
  otherPossibilities: {color: C.textDim, fontSize: 13, marginBottom: 8, fontStyle: 'italic'},
  checkFirstBox: {
    backgroundColor: C.bg, borderRadius: 8, padding: 12, marginTop: 4,
  },
  checkFirstItem: {color: C.accent, fontSize: 13, lineHeight: 22},

  // Urgency
  urgencyBadge: {
    borderRadius: 8, padding: 10, borderWidth: 1,
    alignSelf: 'flex-start', marginBottom: 8,
  },
  urgencyLevel: {fontSize: 16, fontWeight: '800'},
  urgencyMsg: {color: C.text, fontSize: 14, lineHeight: 21},

  // Cost
  costGrid: {flexDirection: 'row', gap: 8, marginBottom: 8},
  costItem: {
    flex: 1, backgroundColor: C.bg, borderRadius: 8,
    padding: 12, alignItems: 'center',
  },
  costLabel: {
    fontSize: 12, color: C.textDim, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  costValue: {fontSize: 18, fontWeight: '700', color: C.green, marginTop: 4},
  costDealerRow: {
    backgroundColor: C.bg, borderRadius: 8, padding: 12,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 8,
  },
  costNote: {color: C.textDim, fontSize: 12, marginTop: 4},

  // Difficulty
  difficultyRow: {flexDirection: 'row', alignItems: 'center', gap: 12},
  difficultyBadge: {borderRadius: 8, paddingVertical: 6, paddingHorizontal: 14},
  difficultyLevel: {fontSize: 18, fontWeight: '800'},
  difficultyLabel: {color: C.text, fontSize: 14, flex: 1},

  // ShopScript
  shopScriptBox: {
    backgroundColor: C.bg, borderLeftWidth: 3, borderLeftColor: C.accent,
    borderRadius: 8, padding: 16, marginBottom: 12,
  },
  shopScriptText: {
    color: C.textBright, fontSize: 15, lineHeight: 24, fontStyle: 'italic',
  },
  copyBtn: {
    backgroundColor: C.accent + '18', borderRadius: 8, padding: 12,
    alignItems: 'center', borderWidth: 1, borderColor: C.accent + '44',
  },
  copyBtnText: {color: C.accent, fontSize: 14, fontWeight: '600'},

  // Red flags
  redFlagItem: {
    backgroundColor: C.red + '10', borderLeftWidth: 3,
    borderLeftColor: C.red, borderRadius: 8, padding: 12,
    marginBottom: 8,
  },
  redFlagText: {color: C.text, fontSize: 14, lineHeight: 21},

  // Copied toast
  copiedToast: {
    backgroundColor: C.green + '22', borderRadius: 8, padding: 10,
    alignItems: 'center', marginBottom: 12,
    borderWidth: 1, borderColor: C.green + '44',
  },
  copiedText: {color: C.green, fontSize: 13, fontWeight: '600'},

  // Actions
  actionRow: {marginTop: 8, marginBottom: 12},
  shareBtn: {
    backgroundColor: C.card, borderRadius: 12, padding: 14,
    alignItems: 'center', borderWidth: 1, borderColor: C.border,
  },
  shareBtnText: {color: C.textBright, fontSize: 15, fontWeight: '600'},
  backBtn: {
    borderWidth: 1, borderColor: C.accent, borderRadius: 12,
    padding: 14, alignItems: 'center',
  },
  backBtnText: {color: C.accent, fontSize: 15, fontWeight: '600'},

  // Footer
  footer: {alignItems: 'center', marginTop: 24},
  footerBrand: {color: C.gold, fontSize: 12, fontWeight: '700'},
  footerNote: {color: C.textDim, fontSize: 11, marginTop: 2},
});
