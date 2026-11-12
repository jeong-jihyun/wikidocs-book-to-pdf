// 여러 화면에서 같이 쓰는 작은 부품들
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';

export const C = {
  bg: '#f4f7fb',
  card: '#ffffff',
  ink: '#102a43',
  sub: '#627d98',
  line: '#d9e2ec',
  primary: '#1c64f2',
  primaryDark: '#1747b5',
  ok: '#0a7a3d',
  okBg: '#e6f6ec',
  warn: '#9a5b00',
  warnBg: '#fff4e0',
  err: '#b42318',
  errBg: '#fdecea',
};

export function StepBadge({ n, title }: { n: string; title: string }) {
  return (
    <View style={s.badgeRow}>
      <View style={s.badge}>
        <Text style={s.badgeText}>{n}단계</Text>
      </View>
      <Text style={s.badgeTitle}>{title}</Text>
    </View>
  );
}

export function Card({ children, tone }: { children: React.ReactNode; tone?: 'ok' | 'warn' | 'err' }) {
  const bg = tone === 'ok' ? C.okBg : tone === 'warn' ? C.warnBg : tone === 'err' ? C.errBg : C.card;
  return <View style={[s.card, { backgroundColor: bg }]}>{children}</View>;
}

export function Label({ text, hint }: { text: string; hint?: string }) {
  return (
    <View style={{ marginTop: 14, marginBottom: 6 }}>
      <Text style={s.label}>{text}</Text>
      {hint ? <Text style={s.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Field(props: TextInputProps & { label: string; hint?: string }) {
  const { label, hint, style, ...rest } = props;
  return (
    <View>
      <Label text={label} hint={hint} />
      <TextInput
        placeholderTextColor="#9aa5b1"
        autoCapitalize="none"
        autoCorrect={false}
        {...rest}
        style={[s.input, style]}
      />
    </View>
  );
}

export function SwitchRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <View style={s.switchRow}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <Text style={s.label}>{label}</Text>
        {hint ? <Text style={s.hint}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: C.primary, false: '#bcccdc' }} />
    </View>
  );
}

export function Btn({
  title,
  onPress,
  kind = 'primary',
  disabled,
  loading,
}: {
  title: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary' | 'danger' | 'ghost';
  disabled?: boolean;
  loading?: boolean;
}) {
  const off = disabled || loading;
  const bg =
    kind === 'primary' ? C.primary : kind === 'danger' ? C.err : kind === 'secondary' ? '#e8effa' : 'transparent';
  const fg = kind === 'primary' || kind === 'danger' ? '#fff' : C.primary;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={off}
      style={({ pressed }) => [
        s.btn,
        { backgroundColor: bg, opacity: off ? 0.5 : pressed ? 0.85 : 1 },
        kind === 'ghost' && { borderWidth: 1, borderColor: C.line },
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={[s.btnText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Bar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <View style={s.barTrack} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(pct * 100) }}>
      <View style={[s.barFill, { width: `${pct * 100}%` }]} />
    </View>
  );
}

export function Note({ text, tone }: { text: string; tone?: 'ok' | 'warn' | 'err' }) {
  const color = tone === 'ok' ? C.ok : tone === 'warn' ? C.warn : tone === 'err' ? C.err : C.sub;
  return <Text style={{ color, fontSize: 14, lineHeight: 20 }}>{text}</Text>;
}

const s = StyleSheet.create({
  badgeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  badge: { backgroundColor: C.primary, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, marginRight: 8 },
  badgeText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  badgeTitle: { color: C.ink, fontWeight: '700', fontSize: 17 },
  card: {
    borderRadius: 14,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: C.line,
  },
  label: { color: C.ink, fontWeight: '600', fontSize: 15 },
  hint: { color: C.sub, fontSize: 13, marginTop: 2, lineHeight: 18 },
  input: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontSize: 16,
    color: C.ink,
    backgroundColor: '#fff',
    minHeight: 48,
  },
  switchRow: { flexDirection: 'row', alignItems: 'center', marginTop: 14, minHeight: 48 },
  btn: { minHeight: 50, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, marginTop: 10 },
  btnText: { fontSize: 16, fontWeight: '700' },
  barTrack: { height: 12, borderRadius: 6, backgroundColor: '#e1e8f0', overflow: 'hidden' },
  barFill: { height: 12, backgroundColor: C.primary, borderRadius: 6 },
});
