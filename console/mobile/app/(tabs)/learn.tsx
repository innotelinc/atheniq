import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Screen, Card, Chip, ErrorNote, Loading, Muted, Divider } from "@/components/ui";
import { api, errorMessage, priceLabel, type Catalog, type CourseCard } from "@/lib/api";
import { useSession } from "@/lib/session";
import { colors, radius, space, type } from "@/lib/theme";

export default function Browse() {
  const router = useRouter();
  const { learner, staff } = useSession();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [program, setProgram] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setCatalog(await api.catalog());
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const courses = useMemo(() => {
    if (!catalog) return [];
    const needle = query.trim().toLowerCase();
    return catalog.courses.filter((course) => {
      if (program && !course.programs.includes(program)) return false;
      if (!needle) return true;
      return `${course.title} ${course.code} ${course.summary} ${course.department}`
        .toLowerCase()
        .includes(needle);
    });
  }, [catalog, program, query]);

  const greeting = learner ? `Welcome back, ${learner.name.split(" ")[0]}` : "Courses, taken here";

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.brandRow}>
          <View style={styles.monogram}>
            <Text style={styles.monogramText}>A</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.brandName}>{catalog?.brand.name ?? "AthenIQ"}</Text>
            <Text style={styles.brandTag}>{catalog?.brand.tagline ?? "Institute"}</Text>
          </View>
          {staff ? <Chip label="Staff" tone="brand" /> : null}
        </View>

        <Text style={styles.hero}>{greeting}</Text>
        <Text style={styles.heroNote}>
          Read every lesson, keep your place, finish the course and collect the certificate — all
          without opening a laptop.
        </Text>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search courses, codes, subjects"
          placeholderTextColor={colors.faint}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.search}
        />

        {catalog && catalog.programs.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
            <Pressable onPress={() => setProgram(null)}>
              <Chip label="All programs" tone={program === null ? "brand" : "default"} />
            </Pressable>
            {catalog.programs.map((item) => (
              <Pressable key={item.id} onPress={() => setProgram(item.name)}>
                <Chip label={item.name} tone={program === item.name ? "brand" : "default"} />
              </Pressable>
            ))}
          </ScrollView>
        ) : null}

        {loading ? <Loading label="Loading the catalog" /> : null}
        {error ? <ErrorNote message={error} /> : null}

        {!loading && !error ? (
          <>
            <Muted>
              {courses.length} {courses.length === 1 ? "course" : "courses"}
              {program ? ` in ${program}` : ""}
            </Muted>
            {courses.map((course) => (
              <CourseCardView
                key={course.id}
                course={course}
                onPress={() => router.push(`/course/${course.id}`)}
              />
            ))}
          </>
        ) : null}

        {catalog && catalog.programs.length ? (
          <Card style={{ marginTop: space(2) }}>
            <Text style={styles.cardEyebrow}>DEGREE PLANS</Text>
            {catalog.programs.map((item, index) => (
              <View key={item.id}>
                {index > 0 ? <Divider /> : null}
                <View style={styles.programRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.programName}>{item.credential}</Text>
                    <Text style={styles.programMeta}>
                      {item.credits} credits · ${Math.round(item.tuitionPerCreditCents / 100)} per credit
                    </Text>
                  </View>
                </View>
              </View>
            ))}
            <Text style={styles.finePrint}>
              Finish the courses in the app; the registrar awards the credential from the same
              record.
            </Text>
          </Card>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

function CourseCardView({ course, onPress }: { course: CourseCard; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [pressed && { opacity: 0.9 }]}>
      <Card style={styles.courseCard}>
        <View style={styles.courseTop}>
          <Text style={styles.courseCode}>{course.code}</Text>
          <Chip label={`${course.credits} credits`} />
        </View>
        <Text style={styles.courseTitle}>{course.title}</Text>
        <Text style={styles.courseSummary} numberOfLines={3}>
          {course.summary}
        </Text>
        <View style={styles.courseMeta}>
          <Text style={styles.courseMetaText}>
            {course.modules} modules · {course.lessons} lessons · {Math.round(course.minutes / 60)}h
          </Text>
          <Text style={styles.coursePrice}>{priceLabel(course.price)}</Text>
        </View>
      </Card>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { padding: space(5), paddingBottom: space(16), gap: space(3.5) },
  brandRow: { flexDirection: "row", alignItems: "center", gap: space(3) },
  monogram: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    backgroundColor: "rgba(16,185,129,0.14)",
    borderWidth: 1,
    borderColor: "rgba(16,185,129,0.35)",
    alignItems: "center",
    justifyContent: "center",
  },
  monogramText: { color: colors.brand, fontWeight: "800", fontSize: 18 },
  brandName: { ...type.heading, color: colors.ink },
  brandTag: { ...type.tiny, color: colors.faint, textTransform: "uppercase", letterSpacing: 1 },
  hero: { ...type.display, color: colors.ink, marginTop: space(2) },
  heroNote: { ...type.body, color: colors.soft, marginTop: space(-1.5) },
  search: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    color: colors.ink,
    paddingHorizontal: space(4),
    paddingVertical: space(3.5),
    fontSize: 16,
  },
  chips: { gap: space(2), paddingVertical: space(0.5) },
  courseCard: { gap: space(2) },
  courseTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  courseCode: { ...type.tiny, color: colors.brandSoft, letterSpacing: 1.2, fontWeight: "700" },
  courseTitle: { ...type.title, color: colors.ink, fontSize: 20, lineHeight: 26 },
  courseSummary: { ...type.small, color: colors.soft, lineHeight: 20 },
  courseMeta: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  courseMetaText: { ...type.small, color: colors.faint },
  coursePrice: { ...type.small, color: colors.ink, fontWeight: "700" },
  cardEyebrow: { ...type.tiny, color: colors.faint, fontWeight: "700", letterSpacing: 1.2, marginBottom: space(3) },
  programRow: { paddingVertical: space(2.5) },
  programName: { ...type.small, color: colors.ink, fontWeight: "600" },
  programMeta: { ...type.small, color: colors.faint, marginTop: 2 },
  finePrint: { ...type.small, color: colors.faint, marginTop: space(3), lineHeight: 18 },
});
