import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { rmSync } from 'node:fs';
import assert from 'node:assert/strict';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-transaction-direction.mjs');
execFileSync(join(root,'node_modules','.bin','esbuild'),[join(root,'src/lib/transactionDirection.ts'),'--format=esm',`--outfile=${out}`]);
try {
 const { transactionIsCredit: direction }=await import(out);
 for (const [row,kind,expected] of [
  [{type:'debit',amount:100},'cash',false],
  [{type:'credit',amount:100},'cash',true],
  [{type:'earn',source:'hp_transfer',amount:25},'hp',true],
  [{type:'spend',source:'hp_transfer',amount:25},'hp',false],
  [{source:'transfer_received',amount:25},'hp',true],
  [{source:'transfer_out',amount:25},'hp',false],
  [{source:'food_order',amount:25},'hp',true],
  [{type:'credit',amount:-100},'cash',false],
  [{reference_type:'order_payment',amount:100},'cash',false],
  [{source:'hp_decay_applied',amount:25},'hp',false],
 ]) assert.equal(direction(row,kind),expected,JSON.stringify(row));
 console.log('PASS 10 ledger direction cases: signed amounts, positive debits, HP transfer in/out and expiry');
} finally {rmSync(out,{force:true});}
