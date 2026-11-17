import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import {
  Body,
  Button,
  Card,
  Chip,
  Divider,
  ErrorNote,
  Field,
  Heading,
  Loading,
  Muted,
  Screen,
  Stat,
} from "@/components/ui";
import { api, errorMessage, type RegistrarOverview } from "@/lib/api";
import { useSession } from "@/lib/session";
import { colors, space, type } from "@/lib/theme";

export default function RegistrarScreen() {
  const { staff, learner, signInStaff, signOut } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [data, setData] = useState<RegistrarOverview | null>(null);
  const [issuing, setIssuing] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!staff) return;
    try {
      setData(await api.registrar(staff.token));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [staff]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.staffLogin({ email, password, code: code || undefined });
      await signInStaff(result);
      setPassword("");
      setCode("");
    } catch (caught) {
      const message = errorMessage(caught);
      if (message.toLowerCase().includes("authenticator")) setNeedsCode(true);
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const act = async (purchaseId: string, action: "confirm" | "grant" | "decline") => {
    if (!staff) return;
    setActing(purchaseId);
    try {
      await api.registrarPurchase(staff.token, purchaseId, action);
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setActing(null);
    }
  };

  const issue = async (credentialId: string) => {
    if (!staff) return;
    setIssuing(credentialId);
    try {
      await api.issue(staff.token, credentialId);
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIssuing(null);
    }
  };

  if (!staff) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.eyebrow}>REGISTRAR CONSOLE</Text>
          <Text style={styles.title}>The school, in your hand</Text>
          <Body>
            Sign in with a staff account to watch enrollments, see what learners finished, and issue
            the certificates the app queued.
          </Body>

          <Card style={{ gap: space(3) }}>
            <Field
              label="Staff email"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              textContentType="username"
              placeholder="you@innotel.us"
            />
            <Field
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              textContentType="password"
              placeholder="••••••••"
            />
            <Field
              label={needsCode ? "Authenticator code" : "Authenticator code (if enrolled)"}
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              placeholder="123 456"
              hint="Six digits, or one of your recovery codes."
            />
            {error ? <ErrorNote message={error} /> : null}
            <Button label="Sign in to the console" onPress={submit} loading={busy} />
          </Card>

          {learner ? (
            <Muted>
              You are signed in as a learner ({learner.name}). Signing in here switches the app to
              the staff account; your learner session returns when you sign in as a learner again.
            </Muted>
          ) : (
            <Muted>Registrars and publishers only. Learners sign up under Account.</Muted>
          )}
        </ScrollView>
      </Screen>
    );
  }

  if (!data && !error) {
    return (
      <Screen>
        <View style={styles.content}>
          <Loading label="Reading the school record" />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.eyebrow}>REGISTRAR CONSOLE</Text>
        <Text style={styles.title}>{staff.name}</Text>
        <Muted>
          {staff.staffRole === "registrar" ? "Registrar" : "Publisher"} · {staff.email}
        </Muted>

        {error ? <ErrorNote message={error} /> : null}

        {data ? (
          <>
            <Card style={styles.statsCard}>
              <View style={styles.statsRow}>
                <Stat label="Learners" value={data.counts.learners} />
                <Stat label="Active" value={data.counts.active} />
              </View>
              <Divider />
              <View style={styles.statsRow}>
                <Stat label="Completions" value={data.counts.completions} />
                <Stat label="To issue" value={data.counts.certificatesQueued} />
              </View>
              <Divider />
              <View style={styles.statsRow}>
                <Stat label="Issued" value={data.counts.certificatesIssued} />
                <Stat label="Published" value={data.counts.publishedCourses} />
              </View>
            </Card>

            <Text style={styles.section}>PAYMENTS WAITING</Text>
            {data.purchases.length ? (
              data.purchases.map((purchase) => (
                <Card key={purchase.id} style={{ gap: space(2) }}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.itemTitle}>{purchase.learner}</Text>
                    <Chip
                      label={purchase.status === "claimed" ? "claimed" : "not paid yet"}
                      tone={purchase.status === "claimed" ? "warn" : "default"}
                    />
                  </View>
                  <Text style={styles.itemSub}>{purchase.course}</Text>
                  <Muted>
                    {purchase.amountCents
                      ? `$${(purchase.amountCents / 100).toFixed(2)} · ref ${purchase.reference}`
                      : `Plan entitlement · ref ${purchase.reference}`}
                    {purchase.note ? ` · “${purchase.note}”` : ""}
                  </Muted>
                  <View style={styles.actionRow}>
                    <Button
                      label="Confirm payment"
                      onPress={() => act(purchase.id, "confirm")}
                      loading={acting === purchase.id}
                    />
                    <Button
                      label="Grant without payment"
                      variant="ghost"
                      onPress={() => act(purchase.id, "grant")}
                      loading={acting === purchase.id}
                    />
                  </View>
                  <Button
                    label="Decline claim"
                    variant="quiet"
                    onPress={() => act(purchase.id, "decline")}
                    loading={acting === purchase.id}
                  />
                </Card>
              ))
            ) : (
              <Empty2 text="No payments are waiting. A priced course appears here as soon as a learner enrolls." />
            )}

            <Text style={styles.section}>CERTIFICATE QUEUE</Text>
            {data.queue.length ? (
              data.queue.map((item) => (
                <Card key={item.id} style={{ gap: space(2) }}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.itemTitle}>{item.learner}</Text>
                    <Chip
                      label={item.status === "issued" ? "Issued" : item.status.replace("_", " ")}
                      tone={item.status === "issued" ? "brand" : "warn"}
                    />
                  </View>
                  <Text style={styles.itemSub}>{item.title}</Text>
                  <Muted>
                    {item.email} · {item.detail || "queued"} · verification {item.verifyId}
                  </Muted>
                  {item.status !== "issued" && staff.staffRole === "registrar" ? (
                    <Button
                      label="Issue certificate"
                      onPress={() => issue(item.id)}
                      loading={issuing === item.id}
                    />
                  ) : null}
                </Card>
              ))
            ) : (
              <Empty2 text="Nothing waiting. Certificates appear here the moment a learner finishes a course." />
            )}

            <Text style={styles.section}>RECENT LEARNERS</Text>
            <Card style={{ paddingVertical: space(1) }}>
              {data.recentLearners.map((person, index) => (
                <View key={person.id}>
                  {index > 0 ? <Divider /> : null}
                  <View style={styles.personRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>{person.name}</Text>
                      <Muted>{person.email}</Muted>
                    </View>
                    <Chip label={`${person.courses} course${person.courses === 1 ? "" : "s"}`} />
                  </View>
                </View>
              ))}
            </Card>

            <Text style={styles.section}>ACTIVITY</Text>
            {data.activity.map((entry) => (
              <View key={entry.id} style={styles.activityRow}>
                <Text style={styles.activityTime}>
                  {new Date(entry.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </Text>
                <Text style={styles.activityText}>{entry.message}</Text>
              </View>
            ))}
          </>
        ) : null}

        <Button label="Sign out of the console" variant="ghost" onPress={signOut} />
        <Muted>
          Awarding a degree, editing the catalog and integrating Signara stay on the web console at
          registrar.atheniq.institute — the phone is for the decisions that cannot wait.
        </Muted>
      </ScrollView>
    </Screen>
  );
}

function Empty2({ text }: { text: string }) {
  return (
    <Card>
      <Muted>{text}</Muted>
    </Card>
  );
}

const styles = StyleSheet.create({
  content: { padding: space(5), paddingBottom: space(16), gap: space(3.5) },
  eyebrow: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.4 },
  title: { ...type.display, fontSize: 27, lineHeight: 32, color: colors.ink },
  statsCard: { gap: space(3) },
  statsRow: { flexDirection: "row", gap: space(3) },
  section: { ...type.tiny, color: colors.faint, fontWeight: "700", letterSpacing: 1.2, marginTop: space(3) },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(2) },
  itemTitle: { ...type.heading, color: colors.ink, flex: 1 },
  itemSub: { ...type.body, color: colors.soft },
  personRow: { flexDirection: "row", alignItems: "center", gap: space(2), paddingVertical: space(3) },
  actionRow: { flexDirection: "row", gap: space(2) },
  activityRow: { flexDirection: "row", gap: space(3), paddingVertical: space(1.5) },
  activityTime: { ...type.tiny, color: colors.faint, width: 52, paddingTop: 2 },
  activityText: { ...type.small, color: colors.soft, flex: 1, lineHeight: 19 },
});
