import { Link } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { colors, space, type } from "@/lib/theme";

export default function NotFound() {
  return (
    <View style={styles.screen}>
      <Text style={styles.title}>That page is not in the app</Text>
      <Link href="/(tabs)/learn" style={styles.link}>
        Back to the catalog
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.canvas, alignItems: "center", justifyContent: "center", gap: space(3), padding: space(6) },
  title: { ...type.title, color: colors.ink, textAlign: "center" },
  link: { ...type.body, color: colors.brandSoft },
});
