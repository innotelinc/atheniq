import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { SessionProvider } from "@/lib/session";
import { configureNotificationHandler } from "@/lib/push";
import { colors } from "@/lib/theme";

// Banners arrive while the app is open; the handler decides how they appear.
configureNotificationHandler();

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.canvas },
            animation: "slide_from_right",
          }}
        >
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="sign-in" options={{ animation: "slide_from_bottom" }} />
          <Stack.Screen name="sign-up" options={{ animation: "slide_from_bottom" }} />
        </Stack>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
