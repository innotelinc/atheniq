import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import {
  Body,
  Button,
  Card,
  Chip,
  Divider,
  Empty,
  ErrorNote,
  Heading,
  Loading,
  Muted,
  ProgressBar,
  Screen,
  Stat,
} from "@/components/ui";
import { api, errorMessage, type MyLearning } from "@/lib/api";
import { useSession } from "@/lib/session";
import { colors, radius, space, type } from "@/lib/theme";

export default function MyLearningScreen() {
  const router = useRouter();
  const { learner } = useSession();
  const [data, setData] = useState<MyLearning | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!learner) return;
    try {
      setData(await api.me(learner.token));
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [learner]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  if (!learner) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.eyebrow}>MY LEARNING</Text>
          <Text style={styles.title}>Your courses, kept in one place</Text>
          <Body>Sign in to see what you are part-way through, pick up where you stopped, and collect certificates.</Body>
          <Button label="Sign in" onPress={() => router.push("/sign-in")} />
          <Button label="Create an account" variant="ghost" onPress={() => router.push("/sign-up")} />
        </ScrollView>
      </Screen>
    );
  }

  if (!data && !error) {
    return (
      <Screen>
        <View style={styles.content}>
          <Loading label="Loading your learning" />
        </View>
      </Screen>
    );
  }

  const active = data?.enrollments.filter((item) => !item.completedAt) ?? [];
  const finished = data?.enrollments.filter((item) => item.completedAt) ?? [];

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.eyebrow}>MY LEARNING</Text>
        <Text style={styles.title}>{data?.learner.name ?? learner.name}</Text>
        <Muted>
          {data?.learner.programName
            ? `${data.learner.programName} · ${data.learner.email}`
            : data?.learner.email ?? learner.email}
        </Muted>

        {error ? <ErrorNote message={error} /> : null}

        {data ? (
          <Card style={styles.statsCard}>
            <View style={styles.statsRow}>
              <Stat label="Enrolled" value={data.stats.enrolled} />
              <Stat label="Completed" value={data.stats.completed} />
            </View>
            <Divider />
            <View style={styles.statsRow}>
              <Stat label="Credits earned" value={data.stats.credits} />
              <Stat label="Certificates" value={data.stats.certificates} />
            </View>
          </Card>
        ) : null}

        {active.length ? (
          <>
            <Text style={styles.section}>CONTINUE</Text>
            {active.map((item) => (
              <Pressable key={item.id} onPress={() => router.push(`/course/${item.course.id}`)}>
                <Card style={{ gap: space(2) }}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.code}>{item.course.code}</Text>
                    <Text style={styles.percent}>{item.progress.percent}%</Text>
                  </View>
                  <Text style={styles.courseTitle}>{item.course.title}</Text>
                  <ProgressBar percent={item.progress.percent} />
                  <Muted>
                    {item.progress.done} of {item.progress.total} lessons
                    {item.progress.nextLessonTitle && item.access !== "pending_payment"
                      ? ` · next: ${item.progress.nextLessonTitle}`
                      : ""}
                  </Muted>
                  {item.access === "pending_payment" ? (
                    <Chip label="Payment pending — lessons locked" tone="warn" />
                  ) : null}
                </Card>
              </Pressable>
            ))}
          </>
        ) : data ? (
          <Empty title="Nothing in progress" note="Pick a course from the catalog and it will wait here between sittings." />
        ) : null}

        {finished.length ? (
          <>
            <Text style={styles.section}>COMPLETED</Text>
            {finished.map((item) => (
              <Pressable key={item.id} onPress={() => router.push(`/course/${item.course.id}`)}>
                <Card style={{ gap: space(1.5) }}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.courseTitle}>{item.course.title}</Text>
                    <Chip label="Done" tone="brand" />
                  </View>
                  <Muted>
                    {item.course.credits} credits · finished {new Date(item.completedAt!).toLocaleDateString()}
                  </Muted>
                </Card>
              </Pressable>
            ))}
          </>
        ) : null}

        {data?.credentials.length ? (
          <>
            <Text style={styles.section}>CREDENTIALS</Text>
            {data.credentials.map((credential) => (
              <Card key={credential.id} style={{ gap: space(1.5) }}>
                <View style={styles.rowBetween}>
                  <Text style={styles.courseTitle}>{credential.subjectLabel}</Text>
                  <Chip
                    label={credential.status === "issued" ? "Issued" : "With the registrar"}
                    tone={credential.status === "issued" ? "brand" : "warn"}
                  />
                </View>
                <Muted>Verification {credential.verifyId}</Muted>
              </Card>
            ))}
          </>
        ) : null}
      </ScrollView>
    </Screen>
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
  code: { ...type.tiny, color: colors.brandSoft, fontWeight: "700", letterSpacing: 1.2 },
  percent: { color: colors.brand, fontWeight: "700", fontSize: 14 },
  courseTitle: { ...type.heading, color: colors.ink, flex: 1 },
});
