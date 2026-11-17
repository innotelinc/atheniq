import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Body, Button, Card, ErrorNote, Field, Muted, Screen } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { colors, space, type } from "@/lib/theme";

export default function SignIn() {
  const router = useRouter();
  const { next } = useLocalSearchParams<{ next?: string }>();
  const { signInLearner } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.login({ email, password });
      await signInLearner(result);
      if (typeof next === "string" && next.startsWith("/")) router.replace(next);
      else router.replace("/(tabs)/learning");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.eyebrow}>LEARNER SIGN-IN</Text>
          <Text style={styles.title}>Welcome back</Text>
          <Body>Your courses, progress and certificates are waiting.</Body>

          <Card style={{ gap: space(3) }}>
            <Field
              label="Email"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              textContentType="emailAddress"
              placeholder="you@example.com"
            />
            <Field
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              textContentType="password"
              placeholder="••••••••"
            />
            {error ? <ErrorNote message={error} /> : null}
            <Button label="Sign in" onPress={submit} loading={busy} disabled={!email || !password} />
          </Card>

          <Button label="Create an account" variant="ghost" onPress={() => router.replace("/sign-up")} />
          <Button label="Not now" variant="quiet" onPress={() => router.back()} />
          <Muted>Staff accounts sign in from the Registrar tab.</Muted>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: space(5), paddingBottom: space(12), gap: space(3.5) },
  eyebrow: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.4, marginTop: space(4) },
  title: { ...type.display, color: colors.ink },
});
