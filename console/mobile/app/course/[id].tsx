import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import {
  Screen,
  Body,
  Button,
  Card,
  Chip,
  Divider,
  ErrorNote,
  Heading,
  Loading,
  Muted,
  ProgressBar,
} from "@/components/ui";
import { api, errorMessage, priceLabel, type CourseDetail, type PurchaseInfo } from "@/lib/api";
import { useSession } from "@/lib/session";
import { downloadCourse, readCourse, removeCourse, type CachedCourse } from "@/lib/offline";
import { colors, radius, space, type } from "@/lib/theme";

export default function CourseScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { learner, staff } = useSession();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [openModule, setOpenModule] = useState<string | null>(null);
  const [pay, setPay] = useState<PurchaseInfo | null>(null);
  const [claimRef, setClaimRef] = useState("");
  const [claimNote, setClaimNote] = useState("");
  const [cached, setCached] = useState<CachedCourse | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [fromCache, setFromCache] = useState(false);

  const load = useCallback(async () => {
    const stored = await readCourse(id);
    setCached(stored);
    try {
      const detail = await api.course(id, learner?.token);
      setCourse(detail);
      setFromCache(false);
      setOpenModule((current) => current ?? detail.modules[0]?.id ?? null);
      setError("");
      if (detail.enrollment?.access === "pending_payment" && learner) {
        try {
          const info = await api.checkout(detail.id, learner.token);
          if (info.required) {
            setPay(info);
            setClaimRef((current) => current || info.reference);
          }
        } catch {
          // The reference is also shown from the enrollment; a missing checkout is not fatal.
        }
      } else {
        setPay(null);
      }
    } catch (caught) {
      if (stored) {
        setCourse(stored.course);
        setFromCache(true);
        setError("");
        setOpenModule((current) => current ?? stored.course.modules[0]?.id ?? null);
      } else {
        setError(errorMessage(caught));
      }
    }
  }, [id, learner]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const enroll = async () => {
    if (!learner) {
      router.push(`/sign-in?next=${encodeURIComponent(`/course/${id}`)}`);
      return;
    }
    setBusy(true);
    try {
      const result = await api.enroll(id, learner.token);
      if (result.checkout?.amountCents || result.checkout?.reference) {
        setPay(result.checkout);
        setClaimRef(result.checkout.reference);
      }
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const openCheckout = async () => {
    if (!pay?.url) return;
    await WebBrowser.openBrowserAsync(pay.url);
    setNotice("Paid? Quote the reference below so the registrar can confirm it.");
  };

  const claim = async () => {
    if (!learner || !course) return;
    setBusy(true);
    try {
      await api.claim(learner.token, course.id, claimRef, claimNote);
      setNotice("Sent. The registrar confirms the payment and the course opens.");
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    if (!learner || !course) return;
    setDownloading(true);
    try {
      const stored = await downloadCourse(course.id, learner.token);
      setCached(stored);
      setNotice(`Downloaded ${stored.lessons.length} lessons for offline reading.`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setDownloading(false);
    }
  };

  const forget = async () => {
    if (!course) return;
    await removeCourse(course.id);
    setCached(null);
    setNotice("Offline copy removed.");
  };

  if (!course && !error) {
    return (
      <Screen>
        <View style={styles.topbar}>
          <BackButton onPress={() => router.back()} />
        </View>
        <Loading label="Opening the course" />
      </Screen>
    );
  }

  if (!course) {
    return (
      <Screen>
        <View style={styles.topbar}>
          <BackButton onPress={() => router.back()} />
        </View>
        <View style={styles.content}>
          <ErrorNote message={error} />
        </View>
      </Screen>
    );
  }

  const enrolled = Boolean(course.enrollment);
  const access = course.enrollment?.access ?? "open";
  const locked = enrolled && access === "pending_payment";
  const progress = course.progress;
  const complete = Boolean(course.enrollment?.completedAt);
  // Only a one-off price is gated; a plan-gated course is open, as the API says.
  const priced = Boolean(course.price.amountCents && course.price.amountCents > 0);

  return (
    <Screen>
      <View style={styles.topbar}>
        <BackButton onPress={() => router.back()} />
        <Text style={styles.topbarCode}>{course.code}</Text>
        <View style={{ width: 36 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.eyebrow}>{course.department.toUpperCase()}</Text>
        <Text style={styles.title}>{course.title}</Text>
        <Body>{course.summary}</Body>

        <View style={styles.chips}>
          <Chip label={`${course.credits} credits`} tone="brand" />
          <Chip label={`Level ${course.level}`} />
          <Chip label={`${course.lessons} lessons`} />
          <Chip label={`${Math.round(course.minutes / 60)} hours`} />
          <Chip label={priceLabel(course.price)} />
        </View>

        {course.programs.length ? <Muted>{course.programs.join(" · ")}</Muted> : null}
        {fromCache ? (
          <View style={styles.offlineBanner}>
            <Text style={styles.offlineText}>
              Offline copy · downloaded {new Date(cached?.downloadedAt ?? "").toLocaleDateString()}
            </Text>
          </View>
        ) : null}

        {!enrolled ? (
          <Card style={{ gap: space(2.5) }}>
            <Heading>{priced ? "Enroll and pay" : "Take this course here"}</Heading>
            <Muted>
              {staff
                ? "Staff accounts browse the catalog; sign in as a learner under Account to enroll."
                : priced
                  ? "Enrolling reserves your place and gives you a reference. The course opens the moment the registrar confirms your payment."
                  : "Enrolling keeps your place across lessons and queues a certificate for the registrar when you finish."}
            </Muted>
            <Button
              label={
                learner
                  ? priced
                    ? `Enroll · ${priceLabel(course.price)}`
                    : "Enroll in this course"
                  : "Sign in to enroll"
              }
              onPress={enroll}
              loading={busy}
            />
          </Card>
        ) : locked && !complete ? (
          <Card style={{ gap: space(2.5) }}>
            <View style={styles.rowBetween}>
              <Heading>Payment pending</Heading>
              <Chip label="Locked" tone="warn" />
            </View>
            <Muted>
              Your place is held. The lessons open when the registrar confirms the payment — nothing
              else is needed from you once you have paid.
            </Muted>
            {pay ? (
              <>
                <View style={styles.referenceBox}>
                  <Text style={styles.referenceLabel}>PAYMENT REFERENCE</Text>
                  <Text style={styles.reference}>{pay.reference}</Text>
                  <Text style={styles.referenceMeta}>
                    {pay.amountCents ? `$${(pay.amountCents / 100).toFixed(2)} due` : "Entitlement required"}
                  </Text>
                </View>
                {pay.url ? <Button label="Open the school checkout" onPress={openCheckout} /> : null}
                {!pay.url ? (
                  <Muted>
                    No hosted checkout is configured for this school, so pay through the registrar&apos;s
                    usual method and quote the reference above.
                  </Muted>
                ) : null}
                <Divider />
                <Text style={styles.promptLabel}>ALREADY PAID?</Text>
                <TextInput
                  value={claimRef}
                  onChangeText={setClaimRef}
                  autoCapitalize="characters"
                  placeholder="Payment reference"
                  placeholderTextColor={colors.faint}
                  style={styles.input}
                />
                <TextInput
                  value={claimNote}
                  onChangeText={setClaimNote}
                  placeholder="How you paid (optional): transfer date, card ending…"
                  placeholderTextColor={colors.faint}
                  style={styles.input}
                />
                <Button label="Send claim to the registrar" onPress={claim} loading={busy} />
              </>
            ) : (
              <Muted>Payment details are being prepared; pull down to refresh in a moment.</Muted>
            )}
          </Card>
        ) : (
          <Card style={{ gap: space(2.5) }}>
            <View style={styles.progressHead}>
              <Heading>{complete ? "Course complete" : "Your progress"}</Heading>
              <Text style={styles.percent}>{progress.percent}%</Text>
            </View>
            <ProgressBar percent={progress.percent} />
            <Muted>
              {progress.done} of {progress.total} lessons
              {complete ? " · certificate queued with the registrar" : ""}
              {access === "granted" ? " · access granted by the registrar" : ""}
            </Muted>
            {!complete && progress.nextLessonId ? (
              <Button
                label={`Continue: ${progress.nextLessonTitle ?? "next lesson"}`}
                onPress={() => router.push(`/lesson/${course.id}/${progress.nextLessonId}`)}
              />
            ) : complete ? (
              <Button
                label="Review the course"
                variant="ghost"
                onPress={() => router.push(`/lesson/${course.id}/${course.modules[0].lessons[0].id}`)}
              />
            ) : null}
            <Divider />
            {cached ? (
              <View style={styles.rowBetween}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.offlineTitle}>Available offline</Text>
                  <Muted>
                    {cached.lessons.length} lessons · {new Date(cached.downloadedAt).toLocaleDateString()}
                  </Muted>
                </View>
                <Button label="Remove" variant="quiet" onPress={forget} />
              </View>
            ) : (
              <Button
                label="Download for offline"
                variant="ghost"
                onPress={download}
                loading={downloading}
              />
            )}
          </Card>
        )}

        {notice ? <View style={styles.notice}><Text style={styles.noticeText}>{notice}</Text></View> : null}
        {error ? <ErrorNote message={error} /> : null}

        <Section title="What you will be able to do">
          {course.outcomes.map((outcome) => (
            <View key={outcome} style={styles.bulletRow}>
              <Text style={styles.bullet}>•</Text>
              <Text style={styles.bulletText}>{outcome}</Text>
            </View>
          ))}
        </Section>

        <Section title="Who it is for">
          <Body>{course.audience}</Body>
          {course.prerequisites.length ? (
            <Muted>Before you start: {course.prerequisites.join("; ")}</Muted>
          ) : null}
        </Section>

        <Section title={`Curriculum · ${course.modules.length} modules`}>
          {course.modules.map((module, index) => {
            const open = openModule === module.id;
            const done = module.lessons.filter((lesson) => lesson.done).length;
            return (
              <Card key={module.id} style={{ gap: space(2) }}>
                <Pressable onPress={() => setOpenModule(open ? null : module.id)}>
                  <View style={styles.moduleHead}>
                    <View style={{ flex: 1 }}>
                      <Muted>MODULE {index + 1}</Muted>
                      <Text style={styles.moduleTitle}>{module.title}</Text>
                    </View>
                    <Text style={styles.moduleCount}>
                      {done}/{module.lessons.length}
                    </Text>
                  </View>
                </Pressable>
                {open ? (
                  <>
                    <Muted>{module.summary}</Muted>
                    <Divider />
                    {module.lessons.map((lesson, lessonIndex) => {
                      const readOnly = !enrolled || locked;
                      return (
                        <Pressable
                          key={lesson.id}
                          disabled={readOnly}
                          onPress={() => router.push(`/lesson/${course.id}/${lesson.id}`)}
                          style={styles.lessonRow}
                        >
                          <Text style={[styles.lessonMark, lesson.done && { color: colors.brand }]}>
                            {lesson.done ? "✓" : String(lessonIndex + 1).padStart(2, "0")}
                          </Text>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.lessonTitle}>{lesson.title}</Text>
                            <Text style={styles.lessonMeta}>
                              {lesson.type} · {lesson.minutes} min
                            </Text>
                          </View>
                          {readOnly ? <Text style={styles.lock}>locked</Text> : <Text style={styles.chevron}>›</Text>}
                        </Pressable>
                      );
                    })}
                    <Text style={styles.assessment}>Assessment: {module.assessment}</Text>
                  </>
                ) : null}
              </Card>
            );
          })}
        </Section>

        <Section title="How you are graded">
          {course.grading.map((item) => (
            <View key={item.component} style={styles.gradeRow}>
              <Text style={styles.bulletText}>{item.component}</Text>
              <Text style={styles.gradeWeight}>{item.weight}%</Text>
            </View>
          ))}
        </Section>

        {course.description ? (
          <Section title="About the course">
            <Body>{course.description}</Body>
          </Section>
        ) : null}

        <Text style={styles.footnote}>
          Course key {course.key} · {course.modules.length} modules · {course.lessons} lessons
        </Text>
      </ScrollView>
    </Screen>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: space(2.5) }}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function BackButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.back}>
      <Text style={styles.backText}>‹</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: space(4),
    paddingVertical: space(2),
  },
  back: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
  },
  backText: { color: colors.ink, fontSize: 24, lineHeight: 26, marginTop: -2 },
  topbarCode: { ...type.tiny, color: colors.faint, fontWeight: "700", letterSpacing: 1.2 },
  content: { paddingHorizontal: space(5), paddingBottom: space(16), gap: space(4) },
  eyebrow: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.4 },
  title: { ...type.display, fontSize: 28, lineHeight: 34, color: colors.ink },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  progressHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(2) },
  percent: { color: colors.brand, fontWeight: "700", fontSize: 15 },
  sectionTitle: { ...type.heading, color: colors.ink, marginTop: space(2) },
  bulletRow: { flexDirection: "row", gap: space(2.5) },
  bullet: { color: colors.brand, fontSize: 16, lineHeight: 24 },
  bulletText: { ...type.body, color: colors.soft, flex: 1 },
  moduleHead: { flexDirection: "row", alignItems: "center", gap: space(2) },
  moduleTitle: { ...type.heading, color: colors.ink, marginTop: 2 },
  moduleCount: { ...type.small, color: colors.faint },
  lessonRow: { flexDirection: "row", alignItems: "center", gap: space(3), paddingVertical: space(2) },
  lessonMark: { ...type.small, color: colors.faint, width: 22, fontWeight: "700" },
  lessonTitle: { ...type.small, color: colors.ink, fontWeight: "600" },
  lessonMeta: { ...type.small, color: colors.faint, marginTop: 2, textTransform: "capitalize" },
  chevron: { color: colors.faint, fontSize: 20 },
  lock: { ...type.tiny, color: colors.faint },
  assessment: { ...type.small, color: colors.faint, marginTop: space(1) },
  gradeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: space(1.5),
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  gradeWeight: { ...type.small, color: colors.ink, fontWeight: "700" },
  footnote: { ...type.tiny, color: colors.faint, marginTop: space(4), lineHeight: 16 },
  referenceBox: {
    borderWidth: 1,
    borderColor: "rgba(245,193,104,0.4)",
    backgroundColor: "rgba(245,193,104,0.06)",
    borderRadius: radius.md,
    padding: space(3),
    gap: space(1),
  },
  referenceLabel: { ...type.tiny, color: colors.warn, fontWeight: "700", letterSpacing: 1.2 },
  reference: { ...type.heading, color: colors.ink, letterSpacing: 1 },
  referenceMeta: { ...type.small, color: colors.soft },
  promptLabel: { ...type.tiny, color: colors.faint, fontWeight: "700", letterSpacing: 1.2 },
  input: {
    backgroundColor: colors.surface2,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    color: colors.ink,
    paddingHorizontal: space(3),
    paddingVertical: space(2.5),
    fontSize: 15,
  },
  offlineBanner: {
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface2,
    paddingHorizontal: space(3),
    paddingVertical: 4,
  },
  offlineText: { ...type.tiny, color: colors.soft, fontWeight: "600" },
  offlineTitle: { ...type.small, color: colors.ink, fontWeight: "600" },
  notice: {
    borderWidth: 1,
    borderColor: "rgba(16,185,129,0.4)",
    backgroundColor: "rgba(16,185,129,0.08)",
    borderRadius: radius.md,
    padding: space(3),
  },
  noticeText: { ...type.small, color: colors.brandSoft, lineHeight: 19 },
});
