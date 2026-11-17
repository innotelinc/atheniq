import AsyncStorage from "@react-native-async-storage/async-storage";
import { api, type CourseDetail, type LessonContent, type OfflineBundle } from "./api";

/**
 * A downloaded course, kept on the phone.
 *
 * The whole course arrives in one response (text, curriculum, course detail) so
 * a commuter can read it with no signal. Progress is deliberately not cached:
 * finishing a lesson still needs the server, so nothing is marked complete off
 * the record.
 */
const PREFIX = "atheniq.offline.";

export interface CachedCourse {
  downloadedAt: string;
  course: CourseDetail;
  lessons: LessonContent[];
}

export async function downloadCourse(courseId: string, token: string): Promise<CachedCourse> {
  const bundle = await api.offline(courseId, token);
  const cached: CachedCourse = {
    downloadedAt: bundle.downloadedAt,
    course: bundle.course,
    lessons: bundle.lessons,
  };
  await AsyncStorage.setItem(`${PREFIX}${courseId}`, JSON.stringify(cached));
  return cached;
}

export async function readCourse(courseId: string): Promise<CachedCourse | null> {
  try {
    const raw = await AsyncStorage.getItem(`${PREFIX}${courseId}`);
    if (!raw) return null;
    return JSON.parse(raw) as CachedCourse;
  } catch {
    return null;
  }
}

export async function removeCourse(courseId: string): Promise<void> {
  await AsyncStorage.removeItem(`${PREFIX}${courseId}`);
}

export async function cachedLesson(
  courseId: string,
  lessonId: string,
): Promise<{ lesson: LessonContent; course: CourseDetail; downloadedAt: string } | null> {
  const cached = await readCourse(courseId);
  if (!cached) return null;
  const lesson = cached.lessons.find((item) => item.id === lessonId);
  if (!lesson) return null;
  return { lesson, course: cached.course, downloadedAt: cached.downloadedAt };
}

/** Re-tick lessons in the cache after progress is saved online. */
export async function applyProgressLocally(
  courseId: string,
  lessonId: string,
  done: boolean,
): Promise<void> {
  const cached = await readCourse(courseId);
  if (!cached) return;
  const lesson = cached.lessons.find((item) => item.id === lessonId);
  if (lesson) lesson.done = done;
  const courseLesson = cached.course.modules
    .flatMap((module) => module.lessons)
    .find((item) => item.id === lessonId);
  if (courseLesson) courseLesson.done = done;
  await AsyncStorage.setItem(`${PREFIX}${courseId}`, JSON.stringify(cached));
}

export async function downloadedCourseIds(): Promise<string[]> {
  try {
    const keys = await AsyncStorage.getAllKeys();
    return keys.filter((key) => key.startsWith(PREFIX)).map((key) => key.slice(PREFIX.length));
  } catch {
    return [];
  }
}

export type { OfflineBundle };
