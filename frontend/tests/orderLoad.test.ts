import assert from 'node:assert/strict';
import test from 'node:test';
import { setTimeout as pause } from 'node:timers/promises';
import { scheduleOrderLoad, type LoadOutcome } from '../src/orderLoad.ts';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function response<T>() {
  const started = deferred<void>();
  const body = deferred<T>();
  return { started: started.promise, ...body, load: () => { started.resolve(); return body.promise; } };
}

test('a delayed unfinished response cannot replace the newer complete results', async () => {
  const first = response<string[]>();
  const second = response<string[]>();
  const shown: LoadOutcome<string[]>[] = [];
  const cancelFirst = scheduleOrderLoad(first.load, (result) => shown.push(result));
  await first.started;
  cancelFirst();
  scheduleOrderLoad(second.load, (result) => shown.push(result));
  await second.started;
  second.resolve(['complete-order']);
  await second.promise;
  first.resolve(['unfinished-order']);
  await first.promise;
  assert.deepEqual(shown, [{ ok: true, value: ['complete-order'] }]);
});

test('a superseded request failure cannot replace current results with an error', async () => {
  const first = response<string[]>();
  const second = response<string[]>();
  const shown: LoadOutcome<string[]>[] = [];
  const cancelFirst = scheduleOrderLoad(first.load, (result) => shown.push(result));
  await first.started;
  cancelFirst();
  scheduleOrderLoad(second.load, (result) => shown.push(result));
  await second.started;
  second.resolve([]);
  await second.promise;
  first.reject(new Error('Old request timed out'));
  await first.promise.catch(() => undefined);
  assert.deepEqual(shown, [{ ok: true, value: [] }]);
});

test('changing a filter cancels publication before the next debounced request starts', async () => {
  const first = response<string[]>();
  const shown: LoadOutcome<string[]>[] = [];
  const cancelFirst = scheduleOrderLoad(first.load, (result) => shown.push(result));
  await first.started;
  cancelFirst();
  first.resolve(['old-customer']);
  await first.promise;
  assert.deepEqual(shown, []);
});

test('unmounting before debounce prevents the request entirely', async () => {
  let calls = 0;
  const cancel = scheduleOrderLoad(async () => { calls += 1; return []; }, () => assert.fail('published after unmount'));
  cancel();
  await pause(5);
  assert.equal(calls, 0);
});

test('the active request still reports failures and a retry can recover', async () => {
  const first = response<string[]>();
  const shown: LoadOutcome<string[]>[] = [];
  const cancelFirst = scheduleOrderLoad(first.load, (result) => shown.push(result));
  await first.started;
  const error = new Error('Current request failed');
  first.reject(error);
  await first.promise.catch(() => undefined);
  assert.deepEqual(shown, [{ ok: false, error }]);
  cancelFirst();
  const retry = response<string[]>();
  scheduleOrderLoad(retry.load, (result) => shown.push(result));
  await retry.started;
  retry.resolve(['requested-order']);
  await retry.promise;
  assert.deepEqual(shown.at(-1), { ok: true, value: ['requested-order'] });
});
