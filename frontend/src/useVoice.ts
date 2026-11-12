import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  defaultDictationLang, dictationError, dictationOptions, isLangCode, languageName, pickVoice, recognitionClass,
  speechChunks, speechLang, speechText, transcriptOf, withDictation, type Recognition,
} from './voice';

// React side of voice input and read-aloud (see voice.ts). Both are off where the browser lacks them.

const LANG_KEY = 'manager-copilot-voice-lang';
const READ_KEY = 'manager-copilot-read-aloud';

function load(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage blocked: fall back to the defaults
  }
}

function keep(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage blocked (e.g. a private window): the choice lasts until the page reloads.
  }
}

/** The browser's preferred languages, most preferred first. */
export const browserLangs = (): readonly string[] =>
  navigator.languages?.length ? navigator.languages : [navigator.language].filter(Boolean);

/** Dictation language and "read answers aloud", kept in this browser only. */
export function useVoicePrefs() {
  const [lang, setLang] = useState<string>(() => {
    const saved = load(LANG_KEY);
    return isLangCode(saved) ? saved : defaultDictationLang(browserLangs());
  });
  const [autoRead, setAutoRead] = useState(() => load(READ_KEY) === 'on');
  useEffect(() => keep(LANG_KEY, lang), [lang]);
  useEffect(() => keep(READ_KEY, autoRead ? 'on' : 'off'), [autoRead]);
  const options = useMemo(() => {
    const list = dictationOptions(browserLangs());
    return list.some((o) => o.code === lang) ? list : [{ code: lang, label: languageName(lang) }, ...list];
  }, [lang]);
  return { lang, setLang, options, autoRead, setAutoRead };
}

/** Speak into the chat box. The text is only filled in; the manager still reviews it and sends. */
export function useDictation(lang: string, onText: (text: string) => void) {
  const [Rec] = useState(() => recognitionClass(window));
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<Recognition | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const start = useCallback((before: string) => {
    if (!Rec || active.current) return;
    const rec = new Rec();
    rec.lang = lang;
    rec.interimResults = true;
    rec.continuous = false; // stops after a pause, like asking one question
    rec.maxAlternatives = 1;
    rec.onresult = (event) => onTextRef.current(withDictation(before, transcriptOf(event.results)));
    rec.onerror = (event) => setError(dictationError(event.error));
    rec.onend = () => {
      active.current = null;
      setListening(false);
    };
    setError(null);
    try {
      rec.start();
      active.current = rec;
      setListening(true);
    } catch {
      setError('Dictation failed.');
    }
  }, [Rec, lang]);

  // Stop listening and keep what was heard so far.
  const stop = useCallback(() => active.current?.stop(), []);
  // Stop listening and drop anything still on its way, e.g. when the message is sent.
  const cancel = useCallback(() => {
    const rec = active.current;
    if (!rec) return;
    rec.onresult = null;
    rec.abort();
  }, []);

  useEffect(() => () => {
    const rec = active.current;
    if (!rec) return;
    rec.onresult = rec.onerror = rec.onend = null;
    rec.abort();
  }, []);

  return { supported: Rec !== null, listening, error, start, stop, cancel };
}

/**
 * Read an answer aloud, one at a time, in the answer's own language. `hint` (the dictation language)
 * settles languages that look alike, such as Malay and Indonesian.
 */
export function useSpeaker(hint: string) {
  const [synth] = useState(() => (typeof window !== 'undefined' && 'speechSynthesis' in window ? window.speechSynthesis : null));
  const [speaking, setSpeaking] = useState<string | null>(null);
  // The language of the last answer that could not be read because no voice for it is installed.
  const [missing, setMissing] = useState<string | null>(null);
  const hintRef = useRef(hint);
  hintRef.current = hint;
  // Cancelling fires the old utterances' end and error events; the run number ignores them.
  const run = useRef(0);

  const stop = useCallback(() => {
    run.current += 1;
    synth?.cancel();
    setSpeaking(null);
    setMissing(null);
  }, [synth]);

  const speak = useCallback((key: string, markdown: string) => {
    if (!synth) return;
    synth.cancel();
    const id = ++run.current;
    const text = speechText(markdown);
    const chunks = speechChunks(text);
    if (chunks.length === 0) {
      setSpeaking(null);
      return;
    }
    const lang = speechLang(text, [hintRef.current, ...browserLangs()]);
    const voices = synth.getVoices();
    const voice = pickVoice(voices, lang);
    // With the voice list loaded and none for this language, another voice would only garble it.
    if (voices.length > 0 && !voice) {
      setSpeaking(null);
      setMissing(languageName(lang, 'en'));
      return;
    }
    setMissing(null);
    const done = () => {
      if (run.current === id) setSpeaking(null);
    };
    setSpeaking(key);
    chunks.forEach((chunk, i) => {
      const utterance = new SpeechSynthesisUtterance(chunk);
      utterance.lang = lang;
      if (voice) utterance.voice = voice;
      utterance.onerror = done;
      if (i === chunks.length - 1) utterance.onend = done;
      synth.speak(utterance);
    });
  }, [synth]);

  useEffect(() => () => synth?.cancel(), [synth]);

  return { supported: synth !== null, speaking, missing, speak, stop };
}
