import { Tabs } from "expo-router";
import { Text } from "react-native";
import { colors } from "@/lib/theme";

function Glyph({ mark, focused }: { mark: string; focused: boolean }) {
  return (
    <Text style={{ fontSize: 18, color: focused ? colors.brand : colors.faint, fontWeight: "700" }}>
      {mark}
    </Text>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.line,
          height: 84,
          paddingTop: 8,
          paddingBottom: 26,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        sceneStyle: { backgroundColor: colors.canvas },
      }}
    >
      <Tabs.Screen
        name="learn"
        options={{
          title: "Courses",
          tabBarIcon: ({ focused }) => <Glyph mark="▤" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="learning"
        options={{
          title: "My learning",
          tabBarIcon: ({ focused }) => <Glyph mark="◈" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="registrar"
        options={{
          title: "Registrar",
          tabBarIcon: ({ focused }) => <Glyph mark="◇" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="account"
        options={{
          title: "Account",
          tabBarIcon: ({ focused }) => <Glyph mark="◎" focused={focused} />,
        }}
      />
    </Tabs>
  );
}
