import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { api } from "./api";

/**
 * Ask for notification permission and hand the device token to the console.
 *
 * A simulator cannot receive push, and a build without an EAS project id cannot
 * mint a token, so both cases explain themselves instead of failing silently.
 */
export async function enableNotifications(sessionToken: string): Promise<{ ok: boolean; message: string }> {
  if (!Device.isDevice) {
    return { ok: false, message: "Push needs a real iPhone; the simulator cannot receive them." };
  }
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "AthenIQ",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== "granted") {
      status = (await Notifications.requestPermissionsAsync()).status;
    }
    if (status !== "granted") {
      return { ok: false, message: "Notifications permission was declined. You can allow it in Settings." };
    }
    const projectId =
      (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId ??
      Constants.easConfig?.projectId;
    const token = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    await api.registerPush(sessionToken, token.data);
    return { ok: true, message: "Notifications are on. We will tell you when a certificate is issued or a course opens." };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown error";
    return {
      ok: false,
      message: `Could not register this device (${detail}). A development build with an EAS project id is needed for push.`,
    };
  }
}

export function configureNotificationHandler(): void {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}
