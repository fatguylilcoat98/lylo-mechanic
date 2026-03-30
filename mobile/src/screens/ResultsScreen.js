import React, {useState} from 'react';
import {View, Text, ScrollView, StyleSheet, TouchableOpacity} from 'react-native';

const SAFETY_COLORS = {
  SAFE_TO_DRIVE: '#3FB950',
  DRIVE_SHORT_DISTANCE_ONLY: '#D29922',
  INSPECT_SOON: '#D29922',
  DO_NOT_DRIVE: '#F85149',
  TOW_RECOMMENDED: '#DA3633',
  EMERGENCY_STOP_IMMEDIATELY: '#FF4444',
};

const CONFIDENCE_COLORS = {
  HIGH: '#3FB950',
  MODERATE: '#D29922',
  LOW: '#F85149',
  VERY_LOW: '#DA3633',
};

const DIY_COLORS = {
  DIY_ALLOWED: '#3FB950',
  DIY_WITH_CAUTION: '#D29922',
  ASSISTED_REPAIR_ONLY: '#D29922',
  PROFESSIONAL_ONLY: '#F85149',
  DANGEROUS_TO_ATTEMPT: '#DA3633',
};

function Section({title, children, color}) {
  return (
    <View style={[s.section, color && {borderLeftColor: color}]}>
      <Text style={s.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function HypothesisCard({hyp, rank}) {
  const [expanded, setExpanded] = useState(false);
  const confPct = Math.round((hyp.confidence_score || 0) * 100);

  return (
    <TouchableOpacity
      style={s.hypCard}
      onPress={() => setExpanded(!expanded)}
      activeOpacity={0.7}>
      <View style={s.hypHeader}>
        <View style={s.hypRank}>
          <Text style={s.hypRankText}>#{rank}</Text>
        </View>
        <View style={s.hypInfo}>
          <Text style={s.hypName}>{hyp.cause_label || hyp.cause_id}</Text>
          <Text style={s.hypBasis}>{hyp.basis}</Text>
        </View>
        <Text style={[
          s.hypConf,
          {color: confPct >= 60 ? '#3FB950' : confPct >= 40 ? '#D29922' : '#8B949E'},
        ]}>
          {confPct}%
        </Text>
      </View>

      {expanded && (
        <View style={s.hypBody}>
          {hyp.evidence?.length > 0 && (
            <View style={s.hypEvidence}>
              <Text style={s.hypSubtitle}>Evidence</Text>
              {hyp.evidence.map((e, i) => (
                <Text key={i} style={s.hypEvidenceItem}>- {e}</Text>
              ))}
            </View>
          )}
          {hyp.what_could_be_wrong && (
            <View style={s.hypCaveat}>
              <Text style={s.hypSubtitle}>Caveat</Text>
              <Text style={s.hypCaveatText}>{hyp.what_could_be_wrong}</Text>
            </View>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

function CostRow({label, low, high, highlight}) {
  return (
    <View style={[s.costRow, highlight && s.costRowHighlight]}>
      <Text style={s.costLabel}>{label}</Text>
      <Text style={[s.costValue, highlight && s.costValueHighlight]}>
        ${low?.toLocaleString()}{high ? ` - $${high.toLocaleString()}` : ''}
      </Text>
    </View>
  );
}

export default function ResultsScreen({route}) {
  const result = route.params?.result;

  if (!result) {
    return (
      <View style={s.container}>
        <Text style={s.errorText}>No diagnosis result available.</Text>
      </View>
    );
  }

  const safetyLevel = result.safety?.level || 'SAFE_TO_DRIVE';
  const safetyColor = SAFETY_COLORS[safetyLevel] || '#8B949E';
  const confLevel = result.confidence?.level || 'MODERATE';
  const confColor = CONFIDENCE_COLORS[confLevel] || '#8B949E';
  const confPct = Math.round((result.confidence?.score || 0) * 100);
  const diyVerdict = result.diy_eligibility?.verdict || 'UNKNOWN';
  const diyColor = DIY_COLORS[diyVerdict] || '#8B949E';

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>
      {/* Safety banner */}
      <View style={[s.safetyBanner, {backgroundColor: safetyColor + '22', borderColor: safetyColor}]}>
        <Text style={[s.safetyLevel, {color: safetyColor}]}>
          {safetyLevel.replace(/_/g, ' ')}
        </Text>
        {result.safety?.reasoning && (
          <Text style={s.safetyReason}>{result.safety.reasoning}</Text>
        )}
        {result.safety?.triggers?.length > 0 && (
          <Text style={s.safetyTriggers}>
            Triggers: {result.safety.triggers.join(', ')}
          </Text>
        )}
      </View>

      {/* Vehicle + Confidence row */}
      <View style={s.topRow}>
        <View style={s.topCard}>
          <Text style={s.topLabel}>Vehicle</Text>
          <Text style={s.topValue}>
            {result.vehicle?.year} {result.vehicle?.make} {result.vehicle?.model}
          </Text>
          <Text style={s.topDetail}>
            {result.vehicle?.odometer?.toLocaleString()} mi
          </Text>
        </View>
        <View style={[s.topCard, {borderLeftColor: confColor}]}>
          <Text style={s.topLabel}>Confidence</Text>
          <Text style={[s.topValue, {color: confColor}]}>{confPct}%</Text>
          <Text style={s.topDetail}>{confLevel}</Text>
        </View>
      </View>

      {/* What We Know */}
      {result.what_we_know?.length > 0 && (
        <Section title="What We Know">
          {result.what_we_know.map((fact, i) => (
            <Text key={i} style={s.bulletItem}>- {fact}</Text>
          ))}
        </Section>
      )}

      {/* Hypotheses */}
      {result.hypotheses?.length > 0 && (
        <Section title="Possible Causes (tap to expand)">
          {result.hypotheses.map((hyp, i) => (
            <HypothesisCard key={hyp.cause_id || i} hyp={hyp} rank={i + 1} />
          ))}
        </Section>
      )}

      {/* Cost Estimates */}
      {result.cost_estimates?.length > 0 && (
        <Section title="Cost Estimates">
          {result.cost_estimates.map((est, i) => (
            <View key={i} style={s.costBlock}>
              <Text style={s.costCause}>{est.cause_label || est.cause_id}</Text>
              {est.diy && (
                <CostRow
                  label="DIY"
                  low={est.diy.parts_low}
                  high={est.diy.parts_high}
                  highlight={diyVerdict === 'DIY_ALLOWED'}
                />
              )}
              {est.shop && (
                <CostRow label="Shop" low={est.shop.total_low} high={est.shop.total_high} />
              )}
              {est.dealer && (
                <CostRow label="Dealer" low={est.dealer.total_low} high={est.dealer.total_high} />
              )}
            </View>
          ))}
        </Section>
      )}

      {/* DIY Eligibility */}
      {result.diy_eligibility && (
        <Section title="DIY Eligibility" color={diyColor}>
          <Text style={[s.diyVerdict, {color: diyColor}]}>
            {diyVerdict.replace(/_/g, ' ')}
          </Text>
          {result.diy_eligibility.skill_level && (
            <Text style={s.diyDetail}>
              Skill: {result.diy_eligibility.skill_level} | Risk: {result.diy_eligibility.risk_level}
            </Text>
          )}
          {result.diy_eligibility.reason && (
            <Text style={s.diyReason}>{result.diy_eligibility.reason}</Text>
          )}
          {result.diy_eligibility.tools_required?.length > 0 && (
            <Text style={s.diyTools}>
              Tools: {result.diy_eligibility.tools_required.join(', ')}
            </Text>
          )}
        </Section>
      )}

      {/* Veracore Flags */}
      {result.veracore_flags?.length > 0 && (
        <Section title="Truth Check Flags">
          {result.veracore_flags.map((flag, i) => (
            <View key={i} style={s.flagRow}>
              <Text style={[
                s.flagSeverity,
                flag.severity === 'critical' && {color: '#F85149'},
                flag.severity === 'caution' && {color: '#D29922'},
              ]}>
                [{flag.severity?.toUpperCase()}]
              </Text>
              <Text style={s.flagMsg}>{flag.message}</Text>
            </View>
          ))}
        </Section>
      )}

      {/* What to Check First */}
      {result.what_to_check_first && (
        <Section title="What to Check First">
          <Text style={s.checkFirst}>{result.what_to_check_first}</Text>
        </Section>
      )}

      {/* Professional Help */}
      {result.professional_triggers?.length > 0 && (
        <Section title="When to See a Mechanic" color="#F85149">
          {result.professional_triggers.map((trigger, i) => (
            <Text key={i} style={s.bulletItem}>- {trigger}</Text>
          ))}
        </Section>
      )}

      <View style={{height: 32}} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#0D1117'},
  content: {padding: 16},
  errorText: {color: '#F85149', fontSize: 16, textAlign: 'center', marginTop: 40},

  // Safety banner
  safetyBanner: {
    borderRadius: 12, padding: 16, marginBottom: 16,
    borderWidth: 1,
  },
  safetyLevel: {fontSize: 18, fontWeight: '800', textTransform: 'uppercase'},
  safetyReason: {color: '#E6EDF3', fontSize: 13, marginTop: 6, lineHeight: 20},
  safetyTriggers: {color: '#8B949E', fontSize: 12, marginTop: 4},

  // Top row
  topRow: {flexDirection: 'row', gap: 10, marginBottom: 16},
  topCard: {
    flex: 1, backgroundColor: '#161B22', borderRadius: 10, padding: 14,
    borderWidth: 1, borderColor: '#21262D', borderLeftWidth: 3,
    borderLeftColor: '#30363D',
  },
  topLabel: {
    color: '#8B949E', fontSize: 11, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 1,
  },
  topValue: {color: '#E6EDF3', fontSize: 18, fontWeight: '700', marginTop: 4},
  topDetail: {color: '#484F58', fontSize: 12, marginTop: 2},

  // Section
  section: {
    backgroundColor: '#161B22', borderRadius: 12, padding: 16,
    marginBottom: 12, borderWidth: 1, borderColor: '#21262D',
    borderLeftWidth: 3, borderLeftColor: '#30363D',
  },
  sectionTitle: {
    color: '#D4A843', fontSize: 13, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10,
  },
  bulletItem: {color: '#E6EDF3', fontSize: 14, lineHeight: 22, marginBottom: 2},

  // Hypothesis
  hypCard: {
    backgroundColor: '#0D1117', borderRadius: 8, padding: 12,
    marginBottom: 8, borderWidth: 1, borderColor: '#21262D',
  },
  hypHeader: {flexDirection: 'row', alignItems: 'center'},
  hypRank: {
    width: 28, height: 28, borderRadius: 14, backgroundColor: '#21262D',
    alignItems: 'center', justifyContent: 'center', marginRight: 10,
  },
  hypRankText: {color: '#D4A843', fontSize: 12, fontWeight: '700'},
  hypInfo: {flex: 1},
  hypName: {color: '#E6EDF3', fontSize: 14, fontWeight: '600'},
  hypBasis: {color: '#484F58', fontSize: 11, marginTop: 1},
  hypConf: {fontSize: 16, fontWeight: '700'},
  hypBody: {marginTop: 10, borderTopWidth: 1, borderTopColor: '#21262D', paddingTop: 10},
  hypSubtitle: {
    color: '#8B949E', fontSize: 11, fontWeight: '700',
    textTransform: 'uppercase', marginBottom: 4,
  },
  hypEvidence: {marginBottom: 8},
  hypEvidenceItem: {color: '#8B949E', fontSize: 12, lineHeight: 18},
  hypCaveat: {},
  hypCaveatText: {color: '#D29922', fontSize: 12, lineHeight: 18, fontStyle: 'italic'},

  // Cost
  costBlock: {marginBottom: 12},
  costCause: {color: '#E6EDF3', fontSize: 14, fontWeight: '600', marginBottom: 6},
  costRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 6, paddingHorizontal: 8,
  },
  costRowHighlight: {backgroundColor: '#0D3D1B22', borderRadius: 6},
  costLabel: {color: '#8B949E', fontSize: 13},
  costValue: {color: '#E6EDF3', fontSize: 13, fontWeight: '600'},
  costValueHighlight: {color: '#3FB950'},

  // DIY
  diyVerdict: {fontSize: 16, fontWeight: '800', marginBottom: 6},
  diyDetail: {color: '#8B949E', fontSize: 13},
  diyReason: {color: '#E6EDF3', fontSize: 13, marginTop: 6, lineHeight: 20},
  diyTools: {color: '#484F58', fontSize: 12, marginTop: 6},

  // Flags
  flagRow: {flexDirection: 'row', marginBottom: 6, alignItems: 'flex-start'},
  flagSeverity: {
    color: '#8B949E', fontSize: 11, fontWeight: '700',
    marginRight: 8, marginTop: 2,
  },
  flagMsg: {color: '#E6EDF3', fontSize: 13, flex: 1, lineHeight: 20},

  // Check first
  checkFirst: {color: '#E6EDF3', fontSize: 14, lineHeight: 22},
});
