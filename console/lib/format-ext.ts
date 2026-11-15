export { money, shortDate, dateTime, daysAgo, humanStatus, statusTone, cx, pct } from "./format";

/** `2027_T1` → `Spring 2027`. */
export function termLabelOf(term: string): string {
  const match = term.match(/^(\d{4})_T(\d)$/);
  if (!match) return term;
  return `${["Spring", "Summer", "Fall", "Winter"][Number(match[2]) - 1]} ${match[1]}`;
}
