/** The console's palette, so the app and the registrar site look like one school. */
export const colors = {
  canvas: "#070f0d",
  surface: "#0d1917",
  surface2: "#122220",
  surface3: "#172c29",
  line: "rgba(117, 168, 152, 0.18)",
  lineStrong: "rgba(117, 168, 152, 0.32)",
  ink: "#eaf4f0",
  soft: "#a7bdb6",
  faint: "#7a908a",
  brand: "#10b981",
  brandDeep: "#059669",
  brandSoft: "#34d399",
  warn: "#f5c168",
  bad: "#f2777a",
  info: "#7cb8f0",
};

export const radius = { sm: 8, md: 12, lg: 18, xl: 24, pill: 999 };

/** 4-point spacing scale. */
export const space = (n: number) => n * 4;

export const type = {
  display: { fontSize: 30, lineHeight: 36, fontWeight: "700" as const, letterSpacing: -0.5 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: "700" as const, letterSpacing: -0.3 },
  heading: { fontSize: 17, lineHeight: 23, fontWeight: "600" as const },
  body: { fontSize: 15.5, lineHeight: 24 },
  small: { fontSize: 13, lineHeight: 18 },
  tiny: { fontSize: 11, lineHeight: 14, letterSpacing: 0.6 },
};
