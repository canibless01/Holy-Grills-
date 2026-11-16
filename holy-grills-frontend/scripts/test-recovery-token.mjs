import assert from 'node:assert/strict';
import { recoveryToken } from '../src/lib/recoveryToken.ts';
assert.equal(recoveryToken('', '#access_token=secret&refresh_token=private&type=recovery'), 'secret');
assert.equal(recoveryToken('?token=legacy', ''), 'legacy');
assert.equal(recoveryToken('', '#access_token=secret&type=signup'), null);
assert.equal(recoveryToken('?token=legacy', '#error=access_denied&error_code=otp_expired'), null);
assert.equal(recoveryToken('', ''), null);
assert.equal(recoveryToken('?token=', '#access_token=&type=recovery'), null);
console.log('Recovery redirect parsing: recovery, legacy, expired and unrelated auth links passed');
