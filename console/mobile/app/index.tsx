import { Redirect } from "expo-router";
import { useSession } from "@/lib/session";

/** The app opens on the catalog; signing in is never the first thing asked. */
export default function Index() {
  const { ready } = useSession();
  if (!ready) return null;
  return <Redirect href="/(tabs)/learn" />;
}
