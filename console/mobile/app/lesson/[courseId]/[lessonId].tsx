import { useCallback, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Button, Card, ErrorNote, Loading, Muted } from "@/components/ui";
import { api, errorMessage, type ContentBlock, type LessonContent } from "@/lib/api";
import { useSession } from "@/lib/session";
import { applyProgressLocally, cachedLesson } from "@/lib/offline";
import { colors, radius, space, type } from "@/lib/theme";

export default function LessonScreen() {
  const { courseId, lessonId } = useLocalSearchParams<{ courseId: string; lessonId: string }>();
  const router = useRouter();
  const { learner, staff } = useSession();
  const [lesson, setLesson] = useState<LessonContent | null>(null);
  const [error, setError] = useState("");
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [offlineSince, setOfflineSince] = useState<string | null>(null);
  const token = learner?.token;

  const load = useCallback(async () => {
    if (!token) {
      router.replace(`/sign-in?next=${encodeURIComponent(`/lesson/${courseId}/${lessonId}`)}`);
      return;
    }
    try {
      const content = await api.lesson(courseId, lessonId, token);
      setLesson(content);
      setAnswer(content.response);
      setOfflineSince(null);
      setError("");
    } catch (caught) {
      // A downloaded course still reads without a network; progress still needs the server.
      const stored = await cachedLesson(courseId, lessonId);
      if (stored) {
        setLesson({
          ...stored.lesson,
          course: {
            id: stored.course.id,
            code: stored.course.code,
            title: stored.course.title,
          },
          response: "",
        });
        setAnswer("");
        setOfflineSince(stored.downloadedAt);
        setError("");
      } else {
        setError(errorMessage(caught));
      }
    }
  }, [courseId, lessonId, router, token]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const mark = async (done: boolean) => {
    if (!lesson) return;
    setSaving(true);
    try {
      const result = await api.progress(token!, {
        courseId,
        lessonId,
        done,
        response: answer.trim() || undefined,
      });
      setLesson({ ...lesson, done, response: answer });
      await applyProgressLocally(courseId, lessonId, done);
      if (result.completedAt) {
        router.replace(`/course/${courseId}`);
        return;
      }
      if (done && lesson.nextLessonId) {
        router.replace(`/lesson/${courseId}/${lesson.nextLessonId}`);
        return;
      }
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  if (!lesson) {
    return (
      <Screen>
        <View style={styles.topbar}>
          <BackButton onPress={() => router.back()} />
        </View>
        <View style={styles.content}>{error ? <ErrorNote message={error} /> : <Loading label="Opening the lesson" />}</View>
      </Screen>
    );
  }

  const position = lesson.position.index + 1;

  return (
    <Screen>
      <View style={styles.topbar}>
        <BackButton onPress={() => router.back()} />
        <Text style={styles.position}>
          {position} of {lesson.position.total}
        </Text>
        <View style={{ width: 36 }} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <Text style={styles.eyebrow}>{lesson.moduleTitle.toUpperCase()}</Text>
          <Text style={styles.title}>{lesson.title}</Text>
          <Muted>
            {lesson.type} · {lesson.minutes} min · {lesson.course.code}
          </Muted>

          {lesson.done ? (
            <View style={styles.doneBanner}>
              <Text style={styles.doneText}>✓ Completed</Text>
            </View>
          ) : null}

          {offlineSince ? (
            <View style={styles.offlineBanner}>
              <Text style={styles.offlineText}>
                Offline copy · downloaded {new Date(offlineSince).toLocaleDateString()} · progress saves
                when you are back online
              </Text>
            </View>
          ) : null}

          {lesson.blocks.map((block, index) => (
            <Block key={`${block.kind}-${index}`} block={block} />
          ))}

          {lesson.needsResponse ? (
            <Card style={{ gap: space(2) }}>
              <Text style={styles.promptLabel}>YOUR ANSWER</Text>
              <Text style={styles.prompt}>{lesson.prompt}</Text>
              <TextInput
                value={answer}
                onChangeText={setAnswer}
                multiline
                placeholder="Write your answer here. It is saved with your course record for the registrar."
                placeholderTextColor={colors.faint}
                style={styles.answer}
              />
              <Muted>{answer.trim().split(/\s+/).filter(Boolean).length} words</Muted>
            </Card>
          ) : null}

          {error ? <ErrorNote message={error} /> : null}

          <Button
            label={lesson.done ? "Save and continue" : "Mark lesson complete"}
            onPress={() => mark(true)}
            loading={saving}
          />
          {lesson.done ? (
            <Button label="Mark as not finished" variant="quiet" onPress={() => mark(false)} disabled={saving} />
          ) : null}

          {!learner && staff ? (
            <Muted>Staff accounts read the catalog; learner progress needs a learner sign-in.</Muted>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function Block({ block }: { block: ContentBlock }) {
  if (block.kind === "heading") return <Text style={styles.heading}>{block.text}</Text>;
  if (block.kind === "quote") return <Text style={styles.quote}>{block.text}</Text>;
  if (block.kind === "lede") return <Text style={styles.lede}>{block.text}</Text>;
  if (block.kind === "paragraph") return <Text style={styles.paragraph}>{block.text}</Text>;
  if (block.kind === "callout") {
    return (
      <View style={styles.callout}>
        {block.label ? <Text style={styles.calloutLabel}>{block.label}</Text> : null}
        <Text style={styles.calloutText}>{block.text}</Text>
      </View>
    );
  }
  if (block.kind === "list") {
    return (
      <View style={{ gap: space(2) }}>
        {(block.items ?? []).map((item) => (
          <View key={item} style={styles.bulletRow}>
            <Text style={styles.bullet}>•</Text>
            <Text style={styles.bulletText}>{item}</Text>
          </View>
        ))}
      </View>
    );
  }
  return (
    <View style={{ gap: space(2.5) }}>
      {(block.items ?? []).map((item, index) => (
        <View key={item} style={styles.stepRow}>
          <Text style={styles.stepNumber}>{index + 1}</Text>
          <Text style={styles.bulletText}>{item}</Text>
        </View>
      ))}
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
  position: { ...type.tiny, color: colors.faint, fontWeight: "700", letterSpacing: 1 },
  content: { paddingHorizontal: space(5), paddingBottom: space(16), gap: space(4) },
  eyebrow: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.2 },
  title: { ...type.title, color: colors.ink, fontSize: 26, lineHeight: 32 },
  heading: { ...type.title, color: colors.ink, fontSize: 19, lineHeight: 25, marginTop: space(2) },
  lede: { ...type.body, fontSize: 17.5, lineHeight: 27, color: colors.ink },
  paragraph: { ...type.body, color: colors.soft },
  quote: {
    ...type.body,
    color: colors.brandSoft,
    fontStyle: "italic",
    borderLeftWidth: 2,
    borderLeftColor: colors.brandDeep,
    paddingLeft: space(3),
  },
  callout: {
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.line,
    padding: space(3.5),
    gap: space(1.5),
  },
  calloutLabel: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1 },
  calloutText: { ...type.small, color: colors.soft, lineHeight: 20 },
  bulletRow: { flexDirection: "row", gap: space(2.5) },
  bullet: { color: colors.brand, fontSize: 15, lineHeight: 23 },
  bulletText: { ...type.body, color: colors.soft, flex: 1 },
  stepRow: { flexDirection: "row", gap: space(3) },
  stepNumber: {
    ...type.small,
    color: colors.canvas,
    backgroundColor: colors.brandDeep,
    width: 20,
    height: 20,
    borderRadius: 10,
    textAlign: "center",
    overflow: "hidden",
    fontWeight: "700",
    lineHeight: 20,
  },
  promptLabel: { ...type.tiny, color: colors.brand, fontWeight: "700", letterSpacing: 1.2 },
  prompt: { ...type.body, color: colors.ink },
  answer: {
    backgroundColor: colors.surface2,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    color: colors.ink,
    padding: space(3),
    fontSize: 15.5,
    lineHeight: 24,
    minHeight: 140,
    textAlignVertical: "top",
  },
  offlineBanner: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface2,
    borderRadius: radius.md,
    padding: space(3),
  },
  offlineText: { ...type.small, color: colors.soft, lineHeight: 19 },
  doneBanner: {
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    backgroundColor: "rgba(16,185,129,0.14)",
    borderWidth: 1,
    borderColor: "rgba(16,185,129,0.4)",
    paddingHorizontal: space(3),
    paddingVertical: 4,
  },
  doneText: { color: colors.brandSoft, fontSize: 12, fontWeight: "700", letterSpacing: 0.6 },
});
