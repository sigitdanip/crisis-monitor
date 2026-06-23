/**
 * safe: this file is documentation + helpers; toLocale appears in JSDoc
 * comments explaining what NOT to use, not as actual calls.
 *
 * Locale-independent date/time formatters.
 * React 19 hydration: Node SSR uses en-US locale, browser may use a different locale
 * (e.g., id-ID). toLocale*() produces different strings server vs client, causing
 * hydration mismatches that crash the dev server HTTP listener.
 *
 * These helpers use toISOString() and hardcoded English arrays only.
 */

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

const WEEKDAYS = [
  "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
] as const;

function toDate(v: Date | string | number): Date {
  return v instanceof Date ? v : new Date(v);
}

/** "2026-06-23 08:30:00 UTC" — full datetime */
export function formatDateTime(v: Date | string | number): string {
  const d = toDate(v);
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

/** "08:30 UTC" — HH:MM only */
export function formatTime(v: Date | string | number): string {
  const d = toDate(v);
  return d.toISOString().slice(11, 16) + " UTC";
}

/** "08:30:00" — HH:MM:SS (no timezone suffix) */
export function formatTimeSec(v: Date | string | number): string {
  const d = toDate(v);
  return d.toISOString().slice(11, 19);
}

/** "2026-06-23" — YYYY-MM-DD */
export function formatDate(v: Date | string | number): string {
  const d = toDate(v);
  return d.toISOString().slice(0, 10);
}

/** "Mon", "Tue", etc. */
export function formatWeekday(v: Date | string | number): string {
  const d = toDate(v);
  return WEEKDAYS[d.getDay()];
}

/** "Jun 20" — abbreviated month + day */
export function formatMonthDay(v: Date | string | number): string {
  const d = toDate(v);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

/** "Jun 20, 14:30" — month + day + HH:MM (for tooltips) */
export function formatMonthDayTime(v: Date | string | number): string {
  const d = toDate(v);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${hh}:${mm}`;
}
