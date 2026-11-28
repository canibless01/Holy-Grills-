import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const temp = await mkdtemp(join(tmpdir(), 'hg-paid-cart-'));
try {
  const file = join(temp, 'paid.mjs');
  await build({entryPoints:['src/lib/paidCart.ts'],bundle:true,format:'esm',platform:'node',outfile:file,
    plugins:[{name:'api-double',setup(build){
      build.onResolve({filter:/^\.\/liveApi$/},()=>({path:'api-double',namespace:'test'}));
      build.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export const liveApi = globalThis.testApi;'}));
    }}]});
  let rows=[], removed=[];
  globalThis.testApi={cart:{get:async()=>({items:rows}),remove:async id=>removed.push(id)}};
  const storage = () => { const rows = new Map(); return {getItem:key => rows.get(key) ?? null,setItem:(key,value) => rows.set(key,value),removeItem:key => rows.delete(key)}; };
  globalThis.window = {localStorage:storage(),sessionStorage:storage()};
  const {rememberPaymentCart,settlePaidCart}=await import(pathToFileURL(file));
  const original={id:'a',menu_item_id:'meal',quantity:1,selected_variations:[],selected_addons:[],notes:'Spicy'};
  const order={id:'order',user_id:'customer',campus_id:'campus',payment_status:'pending'};
  const checkpoint = 'hg_pending_checkout:customer:campus';
  window.localStorage.setItem(checkpoint,JSON.stringify({order_id:order.id}));
  rememberPaymentCart(order,[original]);
  rows=[original];
  assert.equal(await settlePaidCart(order),false); assert.deepEqual(removed,[]);
  assert.ok(window.localStorage.getItem(checkpoint));
  // Retrying checkout cannot replace the original snapshot with edited items.
  rememberPaymentCart(order,[{...original,quantity:2}]);
  rows=[{...original,options:{notes:'Spicy'},notes:undefined},{id:'new',menu_item_id:'extra',quantity:1}];
  await Promise.all([settlePaidCart({...order,payment_status:'paid'}),settlePaidCart({...order,payment_status:'paid'})]);
  assert.deepEqual(removed,['a']);
  assert.equal(window.localStorage.getItem(checkpoint),null);
  assert.equal(await settlePaidCart({...order,payment_status:'paid'}),false);
  removed=[]; const other={...order,id:'edited'};rememberPaymentCart(other,[original]);
  rows=[{...original,quantity:2}];await settlePaidCart({...other,payment_status:'paid'});
  assert.deepEqual(removed,[]);
  console.log('PASS unpaid cart retained; verified payment settles original rows once; new and edited rows survive');
} finally {await rm(temp,{recursive:true,force:true});}
