import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Body, Button, Card, ErrorNote, Field, Muted, Screen } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { colors, space, type } from "@/lib/theme";

export default function SignUp() {
  const router = useRouter();
  const { next } = useLocalSearchParams<{ next?: string }>();
  const { signInLearner } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.register({ name, email, password });
      await signInLearner(result);
      if (typeof next === "string" && next.startsWith("/")) router.replace(next);
      else router.replace("/(tabs)/learn");
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
          <Text style={styles.eyebrow}>NEW ACCOUNT</Text>
          <Text style={styles.title}>Start learning</Text>
          <Body>No application, no fee to browse. Enroll when a course looks like the one you need.</Body>

          <Card style={{ gap: space(3) }}>
            <Field label="Full name" value={name} onChangeText={setName} textContentType="name" placeholder="Ada Lovelace" />
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
              textContentType="newPassword"
              placeholder="At least 8 characters"
              hint="At least 8 characters. Stored as a scrypt hash, never in the clear."
            />
            {error ? <ErrorNote message={error} /> : null}
            <Button
              label="Create my account"
              onPress={submit}
              loading={busy}
              disabled={!name || !email || password.length < 8}
            />
          </Card>

          <Button label="I already have an account" variant="ghost" onPress={() => router.replace("/sign-in")} />
          <Muted>
            This account signs you in as a learner. Staff accounts are created by a registrar in the
            console and sign in from the Registrar tab.
          </Muted>
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
