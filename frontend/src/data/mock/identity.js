import { dates, episodes, documents, hash } from "./fixtures/history.js";

// Derived from fixture identity rather than a sorted list position.
const fromNumber = new Map();
const fromLegacy = new Map();
for (const episode of episodes) {
  for (const date of dates) {
    if (date < episode.start || date > episode.end) continue;
    const legacy = date === episode.end ? episode.id : `${episode.id}~${date}`;
    const value = hash(`issue:${legacy}`) + 1;
    if (fromNumber.has(String(value)))
      throw new Error(`Duplicate mock issue ID: ${legacy}`);
    fromNumber.set(String(value), legacy);
    fromLegacy.set(legacy, value);
    fromLegacy.set(`${episode.id}~${date}`, value);
  }
}
const pages = new Map(documents.map((doc) => [doc.id, doc.source.pageId]));
export const issueId = (legacy) => fromLegacy.get(String(legacy));
export const legacyIssueId = (id) => fromNumber.get(String(id)) || String(id);
export const pageId = (legacy) => pages.get(String(legacy));
