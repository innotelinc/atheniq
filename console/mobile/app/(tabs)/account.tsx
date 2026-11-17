import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Body, Button, Card, Chip, Divider, Muted, Screen } from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { useSession } from "@/lib/session";
import { enableNotifications } from "@/lib/push";
import { colors, space, type } from "@/lib/theme";

export default function AccountScreen() {
  const router = useRouter();
  const { session, learner, staff, signOut } = useSession();
  const [pushNote, setPushNote] = useState("");
  const [pushBusy, setPushBusy] = useState(false);

  const turnOnPush = async () => {
    if (!learner) return;
    setPushBusy(true);
    const result = await enableNotifications(learner.token);
    setPushNote(result.message);
    setPushBusy(false);
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.eyebrow}>ACCOUNT</Text>
        <Text style={styles.title}>{session ? session.name : "Not signed in"}</Text>
        {session ? <Muted>{session.email}</Muted> : <Body>Sign in to enroll, or create an account to start a course.</Body>}

        <Card style={{ gap: space(3) }}>
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Signed in as</Text>
            <Chip
              label={session ? (learner ? "Learner" : "Staff") : "Guest"}
              tone={session ? "brand" : "default"}
            />
          </View>
          <Divider />
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Courses served by</Text>
            <Text style={styles.rowValue}>{API_BASE.replace(/^https?:\/\//, "")}</Text>
          </View>
          {staff ? (
            <>
              <Divider />
              <View style={styles.row}>
                <Text style={styles.rowLabel}>Role</Text>
                <Text style={styles.rowValue}>
                  {staff.staffRole === "registrar" ? "Registrar" : "Publisher"}
                </Text>
              </View>
            </>
          ) : null}
        </Card>

        {!session ? (
          <>
            <Button label="Sign in" onPress={() => router.push("/sign-in")} />
            <Button label="Create an account" variant="ghost" onPress={() => router.push("/sign-up")} />
            <Button label="Staff? Open the registrar tab" variant="quiet" onPress={() => router.push("/(tabs)/registrar")} />
          </>
        ) : (
          <>
            {learner ? (
              <>
                <Button label="Go to my learning" onPress={() => router.push("/(tabs)/learning")} />
                <Button
                  label="Turn on notifications"
                  variant="ghost"
                  onPress={turnOnPush}
                  loading={pushBusy}
                />
                {pushNote ? <Muted>{pushNote}</Muted> : null}
              </>
            ) : (
              <Button label="Open the registrar console" onPress={() => router.push("/(tabs)/registrar")} />
            )}
            <Button label="Sign out" variant="ghost" onPress={signOut} />
          </>
        )}

        <Text style={styles.footnote}>
          AthenIQ · one app for the school and the people it teaches. Certificates are awarded by the
          registrar and verify at {API_BASE.replace(/^https?:\/\//, "")}/verify.
        </Text>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: space(5), paddingBottom: space(16), gap: space(3.5) },
  eyebrow: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.4 },
  title: { ...type.display, fontSize: 27, lineHeight: 32, color: colors.ink },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(3) },
  rowLabel: { ...type.small, color: colors.faint },
  rowValue: { ...type.small, color: colors.ink, fontWeight: "600", flexShrink: 1, textAlign: "right" },
  footnote: { ...type.small, color: colors.faint, lineHeight: 19, marginTop: space(3) },
});
