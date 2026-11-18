import { useEffect } from "react";
import { router, type Href } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";

const FILE = "start-route.txt";

/**
 * Start the app on a given screen, for the screenshot harness.
 *
 * iOS hands launch arguments to native code and JavaScript cannot read
 * NSProcessInfo, so the harness writes the route into the app's Documents
 * directory before launching and this consumes it once. No file, no effect: a
 * normal launch still opens on the catalog, which is why this ships. The short
 * delay lets the root index finish its own redirect first, so the requested
 * screen is the last word rather than a race.
 */
export function useStartRoute() {
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const file = `${FileSystem.documentDirectory}${FILE}`;
        const info = await FileSystem.getInfoAsync(file);
        if (!info.exists) return;
        const route = (await FileSystem.readAsStringAsync(file)).trim();
        await FileSystem.deleteAsync(file, { idempotent: true });
        if (!cancelled && route.startsWith("/")) router.replace(route as Href);
      } catch {
        // A capture hook must never be able to break a launch.
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);
}
