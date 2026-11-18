/** Term helpers shared by the API and the UI. */
export function seedTerm(): string {
  return "2027_T1";
}

export function termOptions(): string[] {
  return ["2027_T1", "2026_T4", "2027_T2", "2027_T3"];
}

/** "2027_T1" reads as "Spring 2027" on the form and in the queue. */
export function termLabel(term: string): string {
  const [year, code] = term.split("_");
  const season: Record<string, string> = { T1: "Spring", T2: "Summer", T3: "Fall", T4: "Winter" };
  return code && season[code] ? `${season[code]} ${year}` : term;
}
