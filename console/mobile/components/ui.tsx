import React from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, radius, space, type } from "@/lib/theme";

export function Screen({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={[styles.screen, style]}>
      {children}
    </SafeAreaView>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <Text style={styles.eyebrow}>{children}</Text>;
}

export function Title({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <Text style={styles.title}>{children}</Text>;
}

export function Display({ children }: { children: React.ReactNode }) {
  return <Text style={styles.display}>{children}</Text>;
}

export function Heading({ children }: { children: React.ReactNode }) {
  return <Text style={styles.heading}>{children}</Text>;
}

export function Body({ children }: { children: React.ReactNode }) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Muted({ children }: { children: React.ReactNode }) {
  return <Text style={styles.muted}>{children}</Text>;
}

export function Chip({ label, tone = "default" }: { label: string; tone?: "default" | "brand" | "warn" | "bad" }) {
  const toneStyle =
    tone === "brand"
      ? { borderColor: "rgba(16,185,129,0.45)", color: colors.brandSoft }
      : tone === "warn"
        ? { borderColor: "rgba(245,193,104,0.45)", color: colors.warn }
        : tone === "bad"
          ? { borderColor: "rgba(242,119,122,0.45)", color: colors.bad }
          : { borderColor: colors.line, color: colors.soft };
  return (
    <View style={[styles.chip, { borderColor: toneStyle.borderColor }]}>
      <Text style={[styles.chipText, { color: toneStyle.color }]}>{label}</Text>
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "ghost" | "quiet";
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.button,
        variant === "primary" && styles.buttonPrimary,
        variant === "ghost" && styles.buttonGhost,
        variant === "quiet" && styles.buttonQuiet,
        isDisabled && { opacity: 0.5 },
        pressed && !isDisabled && { opacity: 0.85 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? colors.canvas : colors.ink} />
      ) : (
        <Text style={[styles.buttonText, variant === "primary" && { color: "#04120d" }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({
  label,
  hint,
  style,
  ...props
}: TextInputProps & { label: string; hint?: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.field, style]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.faint}
        autoCapitalize="none"
        autoCorrect={false}
        style={[styles.input, props.multiline && styles.inputMultiline]}
        {...props}
      />
      {hint ? <Text style={styles.fieldHint}>{hint}</Text> : null}
    </View>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${Math.max(2, Math.min(100, percent))}%` }]} />
    </View>
  );
}

export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <View style={styles.loading}>
      <ActivityIndicator color={colors.brand} />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <View style={styles.error}>
      <Text style={styles.errorText}>{message}</Text>
    </View>
  );
}

export function Empty({ title, note }: { title: string; note: string }) {
  return (
    <Card style={{ alignItems: "center", paddingVertical: space(7) }}>
      <Heading>{title}</Heading>
      <Text style={[styles.muted, { textAlign: "center", marginTop: space(2) }]}>{note}</Text>
    </Card>
  );
}

export function Divider() {
  return <View style={styles.divider} />;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.canvas },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space(4),
  },
  eyebrow: {
    ...type.tiny,
    color: colors.brand,
    textTransform: "uppercase",
    fontWeight: "700",
  },
  display: { ...type.display, color: colors.ink },
  title: { ...type.title, color: colors.ink },
  heading: { ...type.heading, color: colors.ink },
  body: { ...type.body, color: colors.soft },
  muted: { ...type.small, color: colors.faint },
  chip: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space(2.5),
    paddingVertical: 3,
    alignSelf: "flex-start",
  },
  chipText: { fontSize: 11, fontWeight: "600", letterSpacing: 0.3 },
  button: {
    minHeight: 50,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space(4),
  },
  buttonPrimary: { backgroundColor: colors.brand },
  buttonGhost: { borderWidth: 1, borderColor: colors.lineStrong, backgroundColor: colors.surface2 },
  buttonQuiet: { backgroundColor: "transparent" },
  buttonText: { fontSize: 15.5, fontWeight: "700", color: colors.ink },
  field: { gap: space(1.5) },
  fieldLabel: { ...type.tiny, color: colors.faint, textTransform: "uppercase", fontWeight: "700" },
  input: {
    backgroundColor: colors.surface2,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    color: colors.ink,
    paddingHorizontal: space(3.5),
    paddingVertical: space(3),
    fontSize: 16,
  },
  inputMultiline: { minHeight: 130, textAlignVertical: "top", paddingTop: space(3) },
  fieldHint: { ...type.small, color: colors.faint },
  progressTrack: {
    height: 6,
    backgroundColor: colors.surface3,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  progressFill: { height: "100%", backgroundColor: colors.brand, borderRadius: radius.pill },
  stat: { flex: 1, minWidth: "45%" },
  statValue: { fontSize: 26, fontWeight: "700", color: colors.ink, letterSpacing: -0.5 },
  statLabel: { ...type.tiny, color: colors.faint, textTransform: "uppercase", fontWeight: "700", marginTop: 2 },
  loading: { flexDirection: "row", gap: space(2), alignItems: "center", paddingVertical: space(4) },
  error: {
    borderWidth: 1,
    borderColor: "rgba(242,119,122,0.4)",
    backgroundColor: "rgba(242,119,122,0.08)",
    borderRadius: radius.md,
    padding: space(3),
  },
  errorText: { color: colors.bad, fontSize: 13.5, lineHeight: 19 },
  divider: { height: 1, backgroundColor: colors.line },
});
