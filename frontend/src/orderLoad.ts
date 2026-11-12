export type LoadOutcome<T> = { ok: true; value: T } | { ok: false; error: unknown };

/** One filter selection owns its request, including the debounce interval.
 * Cancelling stops publication even when an already-sent HTTP request cannot be stopped.
 */
export function scheduleOrderLoad<T>(
  load: () => Promise<T>,
  publish: (outcome: LoadOutcome<T>) => void,
  delay = 0,
): () => void {
  let active = true;
  const timer = setTimeout(async () => {
    let outcome: LoadOutcome<T>;
    try {
      outcome = { ok: true, value: await load() };
    } catch (error) {
      outcome = { ok: false, error };
    }
    if (active) publish(outcome);
  }, delay);
  return () => {
    active = false;
    clearTimeout(timer);
  };
}
