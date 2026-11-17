import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { api, type LearnerSession, type StaffSession } from "./api";

/**
 * One signed-in person at a time.
 *
 * A learner and a registrar are different accounts, so the app keeps whichever
 * one signed in last and shows the other surface's sign-in when it is missing.
 * The token lives in the iOS keychain (SecureStore) and in localStorage only for
 * the web preview.
 */
const KEY = "atheniq.session";

export interface StoredSession {
  role: "learner" | "staff";
  token: string;
  name: string;
  email: string;
  staffRole?: "registrar" | "publisher";
  programId?: string | null;
}

async function persist(value: StoredSession | null): Promise<void> {
  if (Platform.OS === "web") {
    const store = typeof window !== "undefined" ? window.localStorage : null;
    if (!store) return;
    if (value) store.setItem(KEY, JSON.stringify(value));
    else store.removeItem(KEY);
    return;
  }
  if (value) await SecureStore.setItemAsync(KEY, JSON.stringify(value));
  else await SecureStore.deleteItemAsync(KEY);
}

async function restore(): Promise<StoredSession | null> {
  try {
    const raw =
      Platform.OS === "web"
        ? typeof window !== "undefined"
          ? window.localStorage.getItem(KEY)
          : null
        : await SecureStore.getItemAsync(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    if (!parsed?.token) return null;
    return parsed;
  } catch {
    return null;
  }
}

interface SessionContext {
  ready: boolean;
  session: StoredSession | null;
  learner: StoredSession | null;
  staff: StoredSession | null;
  signInLearner: (result: LearnerSession) => Promise<void>;
  signInStaff: (result: StaffSession) => Promise<void>;
  signOut: () => Promise<void>;
}

const Context = createContext<SessionContext | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<StoredSession | null>(null);

  useEffect(() => {
    restore()
      .then((value) => setSession(value))
      .finally(() => setReady(true));
  }, []);

  const signInLearner = useCallback(async (result: LearnerSession) => {
    const next: StoredSession = {
      role: "learner",
      token: result.token,
      name: result.learner.name,
      email: result.learner.email,
      programId: result.learner.programId,
    };
    await persist(next);
    setSession(next);
  }, []);

  const signInStaff = useCallback(async (result: StaffSession) => {
    const next: StoredSession = {
      role: "staff",
      token: result.token,
      name: result.staff.name,
      email: result.staff.email,
      staffRole: result.staff.role,
    };
    await persist(next);
    setSession(next);
  }, []);

  const signOut = useCallback(async () => {
    await persist(null);
    setSession(null);
  }, []);

  const value = useMemo<SessionContext>(
    () => ({
      ready,
      session,
      learner: session?.role === "learner" ? session : null,
      staff: session?.role === "staff" ? session : null,
      signInLearner,
      signInStaff,
      signOut,
    }),
    [ready, session, signInLearner, signInStaff, signOut],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSession(): SessionContext {
  const value = useContext(Context);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

export async function refreshLearnerName(token: string): Promise<string | null> {
  try {
    const me = await api.me(token);
    return me.learner.name;
  } catch {
    return null;
  }
}
