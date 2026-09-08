/** @odoo-module **/
import {fuzzyTest} from "@web/core/utils/search";

/** Treat Turkish keyboard variants and accents as equivalent. */
export function normalizeMenuName(value) {
  return value
    .toLocaleLowerCase("tr")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ı/g, "i");
}

/** Split names and menu paths into searchable words. */
function getWords(value) {
  return normalizeMenuName(value).match(/[\p{L}\p{N}]+/gu) || [];
}

/** Bounded edit distance including adjacent swapped letters. */
function getEditDistance(source, target, limit) {
  let previous = Array.from({length: target.length + 1}, (_, i) => i);
  let beforePrevious = null;
  for (let i = 1; i <= source.length; i++) {
    const current = [i];
    let minimum = i;
    for (let j = 1; j <= target.length; j++) {
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (source[i - 1] === target[j - 1] ? 0 : 1)
      );
      if (
        i > 1 &&
        j > 1 &&
        source[i - 1] === target[j - 2] &&
        source[i - 2] === target[j - 1]
      ) {
        current[j] = Math.min(current[j], beforePrevious[j - 2] + 1);
      }
      minimum = Math.min(minimum, current[j]);
    }
    if (minimum > limit) return limit + 1;
    beforePrevious = previous;
    previous = current;
  }
  return previous[target.length];
}

/** Prefer exact names and prefixes; use typo/abbreviation matches as fallback. */
function getBestWordScore(token, words) {
  let best = 0;
  for (const word of words) {
    if (word === token) return 100;
    if (word.startsWith(token)) {
      best = Math.max(best, 85);
    } else if (token.length >= 3 && word.includes(token)) {
      best = Math.max(best, 65);
    } else {
      // Short queries are too ambiguous for spelling correction.
      const limit = token.length >= 7 ? 2 : token.length >= 4 ? 1 : 0;
      if (limit && Math.abs(token.length - word.length) <= limit) {
        const distance = getEditDistance(token, word, limit);
        if (distance <= limit) best = Math.max(best, 50 - distance * 8);
      }
      if (
        token.length >= 3 &&
        token[0] === word[0] &&
        token.length / word.length >= 0.4 &&
        fuzzyTest(token, word)
      ) {
        best = Math.max(best, 25);
      }
    }
  }
  return best;
}

/** Rank actionable menus, requiring every query word to match. */
export function searchMenuEntries(entries, query, currentAppId) {
  const tokens = [...new Set(getWords(query))];
  if (!tokens.length) return entries;
  const phrase = tokens.join(" ");
  const results = [];
  for (const entry of entries) {
    const nameWords = getWords(entry.menu.name);
    const pathWords = getWords(entry.path);
    const name = nameWords.join(" ");
    let score = 0;
    let nameMatches = 0;
    for (const token of tokens) {
      const nameScore = getBestWordScore(token, nameWords);
      const pathScore = getBestWordScore(token, pathWords) * 0.4;
      const best = Math.max(nameScore, pathScore);
      if (!best) {
        score = 0;
        break;
      }
      score += best;
      if (nameScore >= pathScore) nameMatches++;
    }
    if (!score) continue;
    if (name === phrase) score += 400;
    else if (name.startsWith(phrase)) score += 200;
    else if (name.includes(phrase)) score += 100;
    if (nameMatches === tokens.length) score += 80;
    if (currentAppId && entry.menu.appID === currentAppId) score += 5;
    results.push({entry, score});
  }
  results.sort(
    (a, b) =>
      b.score - a.score ||
      a.entry.path.length - b.entry.path.length ||
      a.entry.menu.name.localeCompare(b.entry.menu.name, "tr")
  );
  return results.map(({entry}) => entry);
}
