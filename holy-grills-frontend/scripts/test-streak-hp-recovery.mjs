import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/streakRecovery.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const { recoverStreakAndHp } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);

const calls = [];
let finishAttendance;
const attendance = new Promise(resolve => { finishAttendance = resolve; });
const recovery = recoverStreakAndHp(
  () => { calls.push('attendance:start'); return attendance.then(() => calls.push('attendance:committed')); },
  async () => { calls.push('streak:read'); return { consecutive_weeks: 1 }; },
  async () => { calls.push('hp:read'); return { pending: 25 }; },
);
await new Promise(resolve => setTimeout(resolve, 0));
assert.deepEqual(calls, ['attendance:start'], 'HP and streak must wait for attendance');
finishAttendance();
assert.deepEqual(await recovery, {
  streak: { consecutive_weeks: 1 },
  balance: { pending: 25 },
});
assert.deepEqual(calls, [
  'attendance:start', 'attendance:committed', 'streak:read', 'hp:read',
], 'the balance must be read after the attendance transaction commits');

let readAfterFailure = false;
await assert.rejects(recoverStreakAndHp(
  async () => { throw new Error('attendance unavailable'); },
  async () => { readAfterFailure = true; },
  async () => { readAfterFailure = true; },
), /attendance unavailable/);
assert.equal(readAfterFailure, false, 'failed attendance must not trigger misleading recovery reads');

console.log('PASS weekly-streak HP recovery reads pending balance only after attendance commits');
