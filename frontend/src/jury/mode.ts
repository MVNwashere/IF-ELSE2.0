/** Jury mode: the phone app full screen on a judge's own phone, on the demo engine (?jury=1 or `--mode jury`). */
export const JURY = typeof window !== "undefined" &&
  (new URLSearchParams(window.location.search).get("jury") === "1" || import.meta.env.MODE === "jury");

/** The pitch tells the freelance story as Juliette; in jury mode the lotte fixture carries her name. */
export const JURY_RENAMES: Record<string, string> = { Lotte: "Juliette" };

export function renameForJury<T>(value: T): T {
  let text = JSON.stringify(value);
  for (const [from, to] of Object.entries(JURY_RENAMES)) text = text.replace(new RegExp(`\\b${from}\\b`, "g"), to);
  return JSON.parse(text) as T;
}
