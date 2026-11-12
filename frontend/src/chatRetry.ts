import type { Session } from './types';

/** One logical send, kept across uncertain create-session or message responses. */
export interface ChatAttempt {
  message: string;
  sessionId: string | null;
  requestId: string;
  completed: boolean;
}

export function chatAttemptFor(
  ref: { current: ChatAttempt | null }, sessionId: string | null, message: string,
): ChatAttempt {
  const previous = ref.current;
  if (!previous || previous.completed || previous.sessionId !== sessionId || previous.message !== message) {
    ref.current = { message, sessionId, requestId: crypto.randomUUID(), completed: false };
  }
  return ref.current!;
}

interface ChatClient<Response> {
  createSession: (title: string, requestId?: string) => Promise<Session>;
  send: (sessionId: string, message: string, requestId?: string) => Promise<Response>;
}

/** Creation and send each recover their own committed result with the same intent ID. */
export async function sendChatAttempt<Response>(
  attempt: ChatAttempt, client: ChatClient<Response>, onCreated?: (session: Session) => void,
): Promise<Response> {
  if (!attempt.sessionId) {
    const session = await client.createSession(attempt.message.slice(0, 60), attempt.requestId);
    attempt.sessionId = session.id;
    onCreated?.(session);
  }
  const result = await client.send(attempt.sessionId, attempt.message, attempt.requestId);
  attempt.completed = true;
  return result;
}
