import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DICTATION_LANGS, defaultDictationLang, dictationError, dictationOptions, isLangCode, pickVoice, recognitionClass,
  speechChunks, speechLang, speechText, transcriptOf, withDictation,
} from '../src/voice.ts';

test('an answer is read as plain sentences', () => {
  const answer = [
    '## ORD-062 is **at risk**',
    '',
    '- Stage: `sewing` → packing',
    '1. Due 2026-04-03 · not_moved_by watch',
    '',
    '| Order | Stage |',
    '|---|:---:|',
    '| ORD-062 | Sewing |',
    '',
    '```json',
    '{"skip": true}',
    '```',
    'See [the evidence](#/orders)',
  ].join('\n');
  assert.equal(
    speechText(answer),
    'ORD-062 is at risk. Stage: sewing to packing. Due 2026-04-03, not moved by watch. Order, Stage. ORD-062, Sewing. See the evidence.',
  );
});

test('Chinese lines end with a Chinese full stop', () => {
  assert.equal(speechText('**ORD-062** 还在裁剪\n明天再看'), 'ORD-062 还在裁剪。 明天再看。');
});

test('each answer is read in its own language, whatever the script', () => {
  const cases: [string, string][] = [
    ['ORD-062 (Bright Basics, 2000 Scarf) is at KNITTING, due 2026-04-08: no risk reasons.', 'en-US'],
    ['ORD-062（Bright Basics）还在 KNITTING 工序，4 月 8 日到期，目前没有风险。', 'zh-CN'],
    ['ORD-062（Bright Basics）還在 KNITTING 工序，4 月 8 日到期，目前沒有風險。', 'zh-TW'],
    ['ORD-062はKNITTING工程にあり、4月8日が納期です。', 'ja-JP'],
    ['ORD-062는 KNITTING 단계에 있으며 4월 8일이 마감입니다.', 'ko-KR'],
    ['ORD-062 находится на этапе KNITTING, срок 2026-04-08, рисков нет.', 'ru-RU'],
    ['الطلب ORD-062 في مرحلة KNITTING، ويستحق في 2026-04-08.', 'ar-SA'],
    ['ORD-062 อยู่ในขั้นตอน KNITTING ครบกำหนด 2026-04-08', 'th-TH'],
    ['ORD-062 KNITTING चरण में है, नियत तिथि 2026-04-08 है।', 'hi-IN'],
    ['ORD-062 KNITTING நிலையில் உள்ளது, 2026-04-08 அன்று முடிவடைகிறது.', 'ta-IN'],
    ["La commande ORD-062 est au stade KNITTING et doit être livrée le 2026-04-08.", 'fr-FR'],
    ['El pedido ORD-062 está en la etapa KNITTING y vence el 2026-04-08. No hay riesgos.', 'es-ES'],
    ['O pedido ORD-062 está na etapa KNITTING e vence em 2026-04-08. Não há riscos.', 'pt-BR'],
    ['Der Auftrag ORD-062 ist in der Phase KNITTING und fällig am 2026-04-08.', 'de-DE'],
    ["L'ordine ORD-062 è nella fase KNITTING e scade il 2026-04-08. Non ci sono rischi.", 'it-IT'],
    ['Đơn hàng ORD-062 đang ở công đoạn KNITTING, hạn 2026-04-08.', 'vi-VN'],
    ['Zamówienie ORD-062 jest na etapie KNITTING, termin 2026-04-08.', 'pl-PL'],
    ['Sipariş ORD-062 KNITTING aşamasında, teslim tarihi 2026-04-08.', 'tr-TR'],
    ['Ang order ORD-062 ay nasa KNITTING at ang due date ay 2026-04-08.', 'fil-PH'],
    ['Packing is behind (包装).', 'en-US'],
    ['2026-04-08', 'en-US'],
  ];
  for (const [text, lang] of cases) assert.equal(speechLang(text), lang, text);
});

test("the manager's language settles languages that look alike", () => {
  const malayOrIndonesian = 'Pesanan ORD-062 sedang di tahap KNITTING dan jatuh tempo pada 2026-04-08. Tidak ada risiko.';
  assert.equal(speechLang(malayOrIndonesian, ['id-ID']), 'id-ID');
  assert.equal(speechLang(malayOrIndonesian, ['ms-MY']), 'ms-MY');
  assert.equal(speechLang('ORD-062 перебуває на етапі KNITTING, термін 2026-04-08.', ['uk-UA']), 'uk-UA');
  assert.equal(speechLang('ORD-062 還喺 KNITTING，4 月 8 號到期。', ['yue-Hant-HK']), 'yue-HK');
  assert.equal(speechLang('請問今天的生產情況怎麼樣？', ['zh-Hans-US']), 'zh-TW');
  assert.equal(speechLang('请问今天的生产情况怎么样？', ['zh-Hans-US']), 'zh-CN');
  assert.equal(speechLang('Order ORD-062 is late.', ['en-SG']), 'en-SG');
  // A hint in another script never overrides the answer's own script.
  assert.equal(speechLang('ORD-062 is late.', ['zh-CN']), 'en-US');
  assert.equal(speechLang('ORD-062 还在裁剪。', ['en-US', 'fr-FR']), 'zh-CN');
});

test('every dictation language is offered, the browser languages first, named in their own language', () => {
  const options = dictationOptions(['zh-CN', 'en-SG', 'en']);
  assert.equal(options.length, DICTATION_LANGS.length);
  assert.deepEqual(options.slice(0, 3).map((o) => o.label), ['中文 (CN)', 'English (SG)', 'English (US)']);
  const label = (code: string) => options.find((o) => o.code === code)?.label;
  assert.equal(label('de-DE'), 'Deutsch'); // one region only: no region shown
  assert.equal(label('ta-SG'), 'தமிழ் (SG)');
  assert.equal(label('yue-Hant-HK'), '粵語');
  assert.equal(new Set(options.map((o) => o.code)).size, options.length);
  // A browser language not in the list is still offered.
  assert.equal(dictationOptions(['cy-GB'])[0].code, 'cy-GB');
});

test('dictation starts in the browser language', () => {
  assert.equal(defaultDictationLang(['zh-CN', 'en']), 'zh-CN');
  assert.equal(defaultDictationLang(['en-SG']), 'en-SG');
  assert.equal(defaultDictationLang(['en']), 'en-US');
  assert.equal(defaultDictationLang(['ms']), 'ms-MY');
  assert.equal(defaultDictationLang([]), 'en-US');
  assert.ok(isLangCode('yue-Hant-HK'));
  assert.ok(!isLangCode('not a language'));
  assert.ok(!isLangCode(null));
});

test('long answers are read in whole sentences of bounded length', () => {
  const text = 'Output fell 12.5% on Tuesday. ' + 'Sewing is the bottleneck this week. '.repeat(12) + 'Check ORD-062 first';
  const chunks = speechChunks(text, 120);
  assert.ok(chunks.length > 1);
  assert.ok(chunks.every((c) => c.length <= 120), chunks.join(' | '));
  assert.equal(chunks[0].startsWith('Output fell 12.5% on Tuesday.'), true); // "12.5" is not a sentence end
  assert.equal(chunks.join(' '), text.trim().replace(/\s+/g, ' '));
});

test('a sentence longer than the limit is split at a space', () => {
  const chunks = speechChunks('word '.repeat(50).trim(), 40);
  assert.ok(chunks.every((c) => c.length <= 40 && !c.startsWith(' ')));
  assert.equal(chunks.join(' ').split(' ').length, 50);
  assert.deepEqual(speechChunks(''), []);
});

test('an installed voice is picked by language, region second', () => {
  const voices = [
    { name: 'Alex', lang: 'en-US' },
    { name: 'Daniel', lang: 'en-GB', default: true },
    { name: 'Tingting', lang: 'zh_CN' },
  ];
  assert.equal(pickVoice(voices, 'en-US')?.name, 'Alex');
  assert.equal(pickVoice(voices, 'zh-CN')?.name, 'Tingting');
  assert.equal(pickVoice(voices, 'en-SG')?.name, 'Daniel');
  assert.equal(pickVoice(voices, 'fr-FR'), undefined);
  // Cantonese: Apple says yue-HK, Chrome elsewhere says zh-HK; a Mandarin voice is not a match.
  const cantonese = [{ name: 'Tingting', lang: 'zh-CN' }, { name: 'Sinji', lang: 'yue-HK' }];
  assert.equal(pickVoice(cantonese, 'yue-HK')?.name, 'Sinji');
  assert.equal(pickVoice([{ name: 'Google 粵語', lang: 'zh-HK' }], 'yue-HK')?.name, 'Google 粵語');
  assert.equal(pickVoice([{ name: 'Tingting', lang: 'zh-CN' }], 'yue-HK'), undefined);
  assert.equal(pickVoice(cantonese, 'zh-TW')?.name, 'Tingting');
});

test('dictation adds to what is already typed', () => {
  assert.equal(withDictation('', ' is ORD-062 late '), 'is ORD-062 late');
  assert.equal(withDictation('Check', 'ORD-062'), 'Check ORD-062');
  assert.equal(withDictation('Check ', 'ORD-062'), 'Check ORD-062');
  assert.equal(withDictation('Check', '  '), 'Check');
  assert.equal(transcriptOf([[{ transcript: 'is order' }], [{ transcript: ' 62 late' }]]), 'is order 62 late');
});

test('dictation errors read as short messages; a stop is not an error', () => {
  assert.equal(dictationError('aborted'), null);
  assert.equal(dictationError('not-allowed'), 'Microphone blocked.');
  assert.equal(dictationError('something-new'), 'Dictation failed.');
});

test('dictation is found under either browser name, or not at all', () => {
  class Rec {}
  assert.equal(recognitionClass({ webkitSpeechRecognition: Rec }), Rec);
  assert.equal(recognitionClass({ SpeechRecognition: Rec }), Rec);
  assert.equal(recognitionClass({}), null);
});
