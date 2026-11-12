// Voice input and read-aloud use the browser's own Web Speech API; the backend never receives audio.
// Dictation runs in the browser maker's speech service (Google for Chrome, Microsoft for Edge, Apple for Safari),
// and read-aloud uses the voices installed on the device. Firefox has no dictation. Any language works:
// dictation takes the language picked under the chat box, and each answer is read in its own language.
// This file holds the pure parts so they can be tested without a browser.

// ---- Languages ------------------------------------------------------------------------------------

/**
 * Dictation languages: every language the main browsers' speech services take, with the regions most
 * people need. The browser's own languages are added if missing. Names come from Intl, not this list.
 */
export const DICTATION_LANGS: readonly string[] = [
  'af-ZA', 'am-ET', 'ar-SA', 'ar-EG', 'ar-AE', 'az-AZ', 'bg-BG', 'bn-BD', 'bn-IN', 'ca-ES', 'cs-CZ', 'da-DK',
  'de-DE', 'el-GR', 'en-US', 'en-GB', 'en-AU', 'en-IN', 'en-SG', 'es-ES', 'es-MX', 'es-US', 'et-EE', 'eu-ES',
  'fa-IR', 'fi-FI', 'fil-PH', 'fr-FR', 'fr-CA', 'gl-ES', 'gu-IN', 'he-IL', 'hi-IN', 'hr-HR', 'hu-HU', 'hy-AM',
  'id-ID', 'is-IS', 'it-IT', 'ja-JP', 'jv-ID', 'ka-GE', 'kk-KZ', 'km-KH', 'kn-IN', 'ko-KR', 'lo-LA', 'lt-LT',
  'lv-LV', 'mk-MK', 'ml-IN', 'mn-MN', 'mr-IN', 'ms-MY', 'my-MM', 'nb-NO', 'ne-NP', 'nl-NL', 'pa-IN', 'pl-PL',
  'pt-BR', 'pt-PT', 'ro-RO', 'ru-RU', 'si-LK', 'sk-SK', 'sl-SI', 'sq-AL', 'sr-RS', 'su-ID', 'sv-SE', 'sw-KE',
  'ta-IN', 'ta-SG', 'te-IN', 'th-TH', 'tr-TR', 'uk-UA', 'ur-PK', 'uz-UZ', 'vi-VN', 'yue-Hant-HK', 'zh-CN',
  'zh-TW', 'zu-ZA',
];

const base = (code: string) => code.split('-')[0].toLowerCase();

/** A well-formed language tag such as "en-SG" or "yue-Hant-HK". */
export function isLangCode(value: unknown): value is string {
  if (typeof value !== 'string' || !value || value.length > 35) return false;
  try {
    return Intl.getCanonicalLocales(value).length === 1;
  } catch {
    return false;
  }
}

/** A language's name, in that language by default ("Deutsch", "中文"), or in `inLang`. */
export function languageName(code: string, inLang = code): string {
  try {
    const name = new Intl.DisplayNames([inLang], { type: 'language' }).of(base(code)) ?? code;
    return name.charAt(0).toLocaleUpperCase(inLang) + name.slice(1);
  } catch {
    return code;
  }
}

export interface LangOption {
  code: string;
  label: string;
}

/** The browser's languages as dictation codes: an exact match, else the same language in another region. */
function browserDictationLangs(preferred: readonly string[]): string[] {
  const out: string[] = [];
  for (const raw of preferred) {
    if (!isLangCode(raw)) continue;
    const code = DICTATION_LANGS.find((c) => c.toLowerCase() === raw.toLowerCase())
      ?? DICTATION_LANGS.find((c) => base(c) === base(raw))
      ?? raw;
    if (!out.includes(code)) out.push(code);
  }
  return out;
}

/** Dictation starts in the browser's first language, or American English. */
export function defaultDictationLang(preferred: readonly string[]): string {
  return browserDictationLangs(preferred)[0] ?? 'en-US';
}

/** The picker: the browser's languages first, then the rest by English name; a region only when needed. */
export function dictationOptions(preferred: readonly string[]): LangOption[] {
  const first = browserDictationLangs(preferred);
  const rest = DICTATION_LANGS.filter((c) => !first.includes(c))
    .map((code, i) => ({ code, i, name: languageName(code, 'en') }))
    .sort((a, b) => a.name.localeCompare(b.name, 'en') || a.i - b.i)
    .map((x) => x.code);
  const all = [...first, ...rest];
  return all.map((code) => {
    const region = code.split('-').slice(1).find((part) => /^([A-Z]{2}|\d{3})$/.test(part));
    const shared = all.filter((c) => base(c) === base(code)).length > 1;
    return { code, label: shared && region ? `${languageName(code)} (${region})` : languageName(code) };
  });
}

// Writing systems that narrow the language down; Latin script is judged by common words below.
// Weight = how many Latin letters one character is worth, so a Chinese answer that quotes
// "ORD-062" and "KNITTING" still counts as Chinese.
const SCRIPTS: { langs: string[]; re: RegExp; weight: number }[] = [
  { langs: ['ko'], re: /[가-힯ᄀ-ᇿ㄰-㆏]/g, weight: 2 },
  { langs: ['ru', 'uk', 'bg', 'sr', 'mk', 'kk', 'mn', 'be'], re: /[Ѐ-ӿ]/g, weight: 1 },
  { langs: ['el'], re: /[Ͱ-Ͽ]/g, weight: 1 },
  { langs: ['he'], re: /[֐-׿]/g, weight: 1 },
  { langs: ['ar', 'fa', 'ur'], re: /[؀-ۿݐ-ݿ]/g, weight: 1 },
  { langs: ['hi', 'mr', 'ne'], re: /[ऀ-ॿ]/g, weight: 1 },
  { langs: ['bn'], re: /[ঀ-৿]/g, weight: 1 },
  { langs: ['pa'], re: /[਀-੿]/g, weight: 1 },
  { langs: ['gu'], re: /[઀-૿]/g, weight: 1 },
  { langs: ['ta'], re: /[஀-௿]/g, weight: 1 },
  { langs: ['te'], re: /[ఀ-౿]/g, weight: 1 },
  { langs: ['kn'], re: /[ಀ-೿]/g, weight: 1 },
  { langs: ['ml'], re: /[ഀ-ൿ]/g, weight: 1 },
  { langs: ['si'], re: /[඀-෿]/g, weight: 1 },
  { langs: ['th'], re: /[฀-๿]/g, weight: 1 },
  { langs: ['lo'], re: /[຀-໿]/g, weight: 1 },
  { langs: ['my'], re: /[က-႟]/g, weight: 1 },
  { langs: ['ka'], re: /[Ⴀ-ჿ]/g, weight: 1 },
  { langs: ['am'], re: /[ሀ-፿]/g, weight: 1 },
  { langs: ['km'], re: /[ក-៿]/g, weight: 1 },
  { langs: ['hy'], re: /[԰-֏]/g, weight: 1 },
];
const KANA = /[぀-ヿ]/g;
const HAN = /[㐀-鿿豈-﫿]/g;
const LATIN = /[A-Za-zÀ-ɏḀ-ỿ]/g;
// Characters written one way in Traditional Chinese and another in Simplified (common in answers here).
const TRADITIONAL = /[們這個會時說經對發還單產貨訂廠數據報過開關進問題實點後與為裡麼風險縫織針裝戶]/g;
const SIMPLIFIED = /[们这个会时说经对发还单产货订厂数据报过开关进问题实点后与为里么风险缝织针装户]/g;

// Common words, and letters only some languages use, for languages written in the Latin alphabet.
const LATIN_LANGS: { lang: string; words: string; letters?: RegExp }[] = [
  { lang: 'en', words: 'a the and is are was of to in for with on not this that it be by has have at due will from order orders' },
  { lang: 'fr', words: 'le la les des est et une un du pour dans pas que qui sur avec au aux ce sont ne commande', letters: /[œàèêëîïûùç]/g },
  { lang: 'es', words: 'el la los las de que y es en un una por para con no del se está están pedido pedidos al', letters: /[ñ¿¡]/g },
  { lang: 'pt', words: 'o os as de que e é em um uma para com não do da dos está são pedido pedidos encomenda', letters: /[ãõ]/g },
  { lang: 'it', words: 'il la di che e è un una per con non del della sono gli nel ordine ordini' },
  { lang: 'de', words: 'der die das und ist nicht ein eine zu mit den von für auf im sind auch noch auftrag bestellung', letters: /[ßäöü]/g },
  { lang: 'nl', words: 'de het een en is van niet dat op voor met zijn te er ook wordt bestelling' },
  { lang: 'ms', words: 'yang dan di ini itu dengan untuk tidak ada dari ke pesanan akan sudah belum boleh kerana sahaja tetapi ialah' },
  { lang: 'id', words: 'yang dan di ini itu dengan untuk tidak ada dari ke pesanan akan sudah belum bisa karena saja tapi adalah' },
  { lang: 'fil', words: 'ang ng mga sa na ay hindi at ito para kung may' },
  { lang: 'vi', words: 'và của là không có đơn hàng được này cho với các', letters: /[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/g },
  { lang: 'tr', words: 'bir ve bu için değil ile çok olarak sipariş daha var yok', letters: /[ğış]/g },
  { lang: 'pl', words: 'nie jest i w na się z do że to oraz zamówienie', letters: /[ąęłńśźż]/g },
  { lang: 'cs', words: 'a je se na že to v není pro s jsou objednávka', letters: /[ěřů]/g },
  { lang: 'ro', words: 'și este în nu de la cu pe că o sunt comanda', letters: /[șțşţ]/g },
  { lang: 'hu', words: 'a az és hogy nem van egy is meg rendelés', letters: /[őű]/g },
  { lang: 'sv', words: 'och är att det som en på inte för med har beställning', letters: /[å]/g },
  { lang: 'da', words: 'og er at det som en på ikke for med har ordre', letters: /[øæå]/g },
  { lang: 'nb', words: 'og er at det som en på ikke for med har ordre bestilling', letters: /[øæå]/g },
  { lang: 'fi', words: 'ja on ei että se mutta ovat ole kanssa tilaus', letters: /[äö]/g },
];
const LATIN_WORDS = LATIN_LANGS.map((l) => ({ ...l, set: new Set(l.words.split(' ')) }));

const count = (text: string, re: RegExp) => text.match(re)?.length ?? 0;

/** Latin-alphabet languages that fit the text, best first; empty when no common word or letter fits. */
function latinCandidates(text: string): string[] {
  const lower = text.toLowerCase();
  const words = lower.match(/\p{L}+/gu) ?? [];
  const scored = LATIN_WORDS.map((l) => ({
    lang: l.lang,
    score: words.filter((w) => l.set.has(w)).length + (l.letters ? 2 * count(lower, l.letters) : 0),
  }));
  const top = Math.max(...scored.map((s) => s.score));
  if (top === 0) return [];
  // Close runners-up stay in, so the manager's own language settles near ties (Malay or Indonesian).
  return scored.filter((s) => s.score >= top * 0.75).sort((a, b) => b.score - a.score).map((s) => s.lang);
}

/**
 * The language to read an answer in. The writing system decides first (Chinese, Japanese, Korean,
 * Cyrillic, Arabic, Thai, Indic scripts…); Latin-alphabet text is matched by common words. Where
 * several languages fit, the first of `hints` that fits wins (the dictation language, then the
 * browser's). Returns a language tag for the speech voice.
 */
export function speechLang(text: string, hints: readonly string[] = []): string {
  const kana = count(text, KANA);
  const han = count(text, HAN);
  const scripts: { langs: string[]; score: number }[] = [
    { langs: [], score: count(text, LATIN) }, // Latin: decided by latinCandidates
    { langs: ['ja'], score: kana >= 2 ? (kana + han) * 3 : 0 },
    { langs: ['zh', 'yue'], score: kana >= 2 ? 0 : han * 3 },
    ...SCRIPTS.map((s) => ({ langs: s.langs, score: count(text, s.re) * s.weight })),
  ];
  const best = scripts.reduce((a, b) => (b.score > a.score ? b : a));
  let candidates = best.langs;
  let fallback = candidates[0];
  if (candidates.length === 0) {
    const fits = latinCandidates(text);
    // Nothing recognisable: any Latin-alphabet language the manager uses, else English.
    candidates = fits.length > 0 ? fits : LATIN_WORDS.map((l) => l.lang);
    fallback = fits[0] ?? 'en';
  }
  const pick = hints.find((h) => isLangCode(h) && candidates.includes(base(h))) ?? fallback;
  if (base(pick) === 'yue') return 'yue-HK';
  // Mandarin: the characters decide between Simplified and Traditional, not a browser tag like zh-Hans-US.
  if (base(pick) === 'zh') return count(text, TRADITIONAL) > count(text, SIMPLIFIED) ? 'zh-TW' : 'zh-CN';
  // A bare language gets its usual region ("fr" → "fr-FR"), so that region's voice is chosen.
  return pick.includes('-') ? pick : DICTATION_LANGS.find((c) => base(c) === pick) ?? pick;
}

/** Markdown answer → plain sentences for a speech voice: no symbols, tables read row by row, code skipped. */
export function speechText(markdown: string): string {
  const out: string[] = [];
  let fenced = false;
  for (const raw of markdown.split('\n')) {
    let line = raw.trim();
    if (line.startsWith('```')) {
      fenced = !fenced;
      continue;
    }
    if (fenced || !line || /^\|?[\s:|-]*-{2,}[\s:|-]*$/.test(line)) continue;
    if (line.startsWith('|')) {
      line = line.replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()).filter(Boolean).join(', ');
    }
    line = line
      .replace(/^#{1,6}\s+/, '')
      .replace(/^>\s?/, '')
      .replace(/^(?:[-*+]|\d+[.)])\s+/, '')
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/`([^`]*)`/g, '$1')
      .replace(/\*\*|__|~~|\*/g, '')
      .replace(/_/g, ' ')
      .replace(/\s*→\s*/g, ' to ')
      .replace(/\s*·\s*/g, ', ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!line) continue;
    if (!/[.!?。！？:;,，；：؟।]$/.test(line)) line += /[\u3040-\u30ff\u3400-\u9fff]$/.test(line) ? '。' : '.';
    out.push(line);
  }
  return out.join(' ');
}

function sentences(text: string): string[] {
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    // A full stop ends a sentence only before a space or the end, so "1.5" and "e.g" stay whole.
    const end = '。！？؟।'.includes(ch) || ('.!?'.includes(ch) && (i + 1 === text.length || /\s/.test(text[i + 1])));
    if (end) {
      out.push(text.slice(start, i + 1).trim());
      start = i + 1;
    }
  }
  out.push(text.slice(start).trim());
  return out.filter(Boolean);
}

function wrap(sentence: string, max: number): string[] {
  const parts: string[] = [];
  let rest = sentence;
  while (rest.length > max) {
    const at = Math.max(rest.lastIndexOf(' ', max), rest.lastIndexOf('，', max), rest.lastIndexOf('、', max), rest.lastIndexOf('،', max));
    const cut = at > 0 ? at + 1 : max;
    parts.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}

/**
 * Whole sentences packed into pieces of at most `max` characters. Chrome stops a long utterance
 * after about 15 seconds, so an answer is read as a queue of short ones.
 */
export function speechChunks(text: string, max = 200): string[] {
  const chunks: string[] = [];
  let current = '';
  for (const sentence of sentences(text)) {
    for (const piece of wrap(sentence, max)) {
      if (current && current.length + 1 + piece.length > max) {
        chunks.push(current);
        current = piece;
      } else {
        current = current ? `${current} ${piece}` : piece;
      }
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

interface VoiceLike {
  lang: string;
  default?: boolean;
}

/** An installed voice for the language: an exact match first, then the same language in another region. */
export function pickVoice<V extends VoiceLike>(voices: readonly V[], lang: string): V | undefined {
  // Cantonese voices are labelled yue-HK on Apple devices and zh-HK elsewhere; never fall back to Mandarin.
  const norm = (l: string) => {
    const tag = l.replace(/_/g, '-').toLowerCase();
    return tag === 'zh-hk' || tag.startsWith('yue') ? 'yue-hk' : tag;
  };
  const want = norm(lang);
  const exact = voices.filter((v) => norm(v.lang) === want);
  const same = exact.length > 0 ? exact : voices.filter((v) => norm(v.lang).split('-')[0] === want.split('-')[0]);
  return same.find((v) => v.default) ?? same[0];
}

/** The text box after dictation: what was typed before, then what was heard. */
export function withDictation(before: string, heard: string): string {
  const said = heard.trim();
  if (!said) return before;
  if (!before.trim()) return said;
  return /\s$/.test(before) ? before + said : `${before} ${said}`;
}

/** Everything heard in one dictation, final and still-changing parts in order. */
export function transcriptOf(results: ArrayLike<ArrayLike<{ transcript: string }>>): string {
  let text = '';
  for (let i = 0; i < results.length; i++) text += results[i][0]?.transcript ?? '';
  return text;
}

/** A short message for a dictation error code; null when the user stopped it. */
export function dictationError(code: string): string | null {
  switch (code) {
    case 'aborted':
      return null;
    case 'no-speech':
      return 'No speech heard.';
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Microphone blocked.';
    case 'audio-capture':
      return 'No microphone found.';
    case 'network':
      return 'Speech service unreachable.';
    case 'language-not-supported':
      return 'Language not supported.';
    default:
      return 'Dictation failed.';
  }
}

/** The part of the browser's SpeechRecognition that the app uses (TypeScript's DOM types omit it). */
export interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

export function recognitionClass(scope: object): (new () => Recognition) | null {
  const s = scope as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return s.SpeechRecognition ?? s.webkitSpeechRecognition ?? null;
}
