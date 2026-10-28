// Finds a cited quote in a PDF page's text-layer items so it can be highlighted.

export interface ItemRange {
  item: number;
  start: number;
  end: number;
}

export interface QuoteMatch {
  kind: 'exact' | 'approximate' | 'none';
  /** One range per text item the match covers, in item order. */
  ranges: ItemRange[];
}

const NONE: QuoteMatch = { kind: 'none', ranges: [] };
const WORD_CHAR = /[\p{L}\p{N}]/u;
/** Share of the quote's words a window must contain to count as an approximate match. */
const APPROXIMATE_THRESHOLD = 0.6;

interface Position {
  item: number;
  offset: number;
}

/**
 * Letters and digits only, lowercased. Comparing on these makes the match ignore whitespace,
 * line breaks, hyphenation ("fine-\ntuning") and punctuation or quote-style differences.
 */
function compact(items: string[]): { text: string; positions: Position[] } {
  let text = '';
  const positions: Position[] = [];
  items.forEach((str, item) => {
    for (let offset = 0; offset < str.length; offset += 1) {
      const ch = str.charAt(offset);
      if (WORD_CHAR.test(ch)) {
        text += ch.toLowerCase();
        positions.push({ item, offset });
      }
    }
  });
  return { text, positions };
}

function toRanges(positions: Position[]): ItemRange[] {
  const ranges: ItemRange[] = [];
  for (const { item, offset } of positions) {
    const last = ranges[ranges.length - 1];
    if (last && last.item === item) last.end = offset + 1;
    else ranges.push({ item, start: offset, end: offset + 1 });
  }
  return ranges;
}

interface Word {
  text: string;
  positions: Position[];
}

function words(items: string[]): Word[] {
  const result: Word[] = [];
  let current: Word | null = null;
  items.forEach((str, item) => {
    for (let offset = 0; offset < str.length; offset += 1) {
      const ch = str.charAt(offset);
      if (WORD_CHAR.test(ch)) {
        current ??= { text: '', positions: [] };
        current.text += ch.toLowerCase();
        current.positions.push({ item, offset });
      } else if (current) {
        result.push(current);
        current = null;
      }
    }
    // Item boundaries end a word unless the line ends in a hyphen ("perfor-" + "mance").
    if (current && !str.endsWith('-')) {
      result.push(current);
      current = null;
    }
  });
  if (current) result.push(current);
  return result;
}

function approximate(items: string[], quote: string): QuoteMatch {
  const quoteWords = words([quote]).map((w) => w.text);
  const pageWords = words(items);
  const size = quoteWords.length;
  if (size === 0 || pageWords.length === 0) return NONE;

  // Clamp window to available page words so we still search short pages.
  const windowSize = Math.min(size, pageWords.length);
  let best = { score: 0, start: 0 };
  for (let start = 0; start + windowSize <= pageWords.length; start += 1) {
    const window = pageWords.slice(start, start + windowSize).map((w) => w.text);
    const pool = [...window];
    let hits = 0;
    for (const word of quoteWords) {
      const index = pool.indexOf(word);
      if (index >= 0) {
        hits += 1;
        pool.splice(index, 1);
      }
    }
    const score = hits / size;
    if (score > best.score) best = { score, start };
  }
  if (best.score < APPROXIMATE_THRESHOLD) return NONE;
  const window = pageWords.slice(best.start, best.start + windowSize);
  return { kind: 'approximate', ranges: toRanges(window.flatMap((w) => w.positions)) };
}

/** Exact match (ignoring layout and punctuation) first, then the best fuzzy window. */
export function findQuote(items: string[], quote: string | undefined): QuoteMatch {
  if (!quote) return NONE;
  const page = compact(items);
  const needle = compact([quote]).text;
  if (!needle) return NONE;
  const index = page.text.indexOf(needle);
  if (index >= 0) {
    return { kind: 'exact', ranges: toRanges(page.positions.slice(index, index + needle.length)) };
  }
  return approximate(items, quote);
}

const escapeHtml = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** HTML for one text-layer item, with the matched span wrapped in <mark class="pdf-hit">. */
export function renderTextItem(str: string, range: ItemRange | undefined): string {
  if (!range) return escapeHtml(str);
  return (
    escapeHtml(str.slice(0, range.start)) +
    `<mark class="pdf-hit">${escapeHtml(str.slice(range.start, range.end))}</mark>` +
    escapeHtml(str.slice(range.end))
  );
}
