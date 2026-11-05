import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rmSync } from 'node:fs';
import assert from 'node:assert/strict';
const root=join(dirname(fileURLToPath(import.meta.url)),'..');
const out=join(root,'node_modules','.cache-install-prompt.mjs');
const events=new EventTarget();
global.window={addEventListener:events.addEventListener.bind(events),dispatchEvent:events.dispatchEvent.bind(events),matchMedia:()=>({matches:false}),navigator:{standalone:false}};
execFileSync(join(root,'node_modules','.bin','esbuild'),[join(root,'src/lib/installPromptStore.ts'),'--format=esm',`--outfile=${out}`]);
try {
 const store=await import(out);
 let notices=0, prompts=0, resolveChoice;
 const unsubscribe=store.subscribeInstallPrompt(()=>notices++);
 const event=new Event('beforeinstallprompt',{cancelable:true});
 event.prompt=async()=>{prompts++};event.userChoice=new Promise(resolve=>resolveChoice=resolve);
 events.dispatchEvent(event);assert.equal(event.defaultPrevented,true);assert.equal(store.hasInstallPrompt(),true);
 const first=store.triggerInstall();assert.equal(store.hasInstallPrompt(),false);
 assert.equal((await store.triggerInstall()).outcome,'unavailable');resolveChoice({outcome:'accepted'});
 assert.equal((await first).outcome,'accepted');assert.equal(prompts,1);
 const failure=new Event('beforeinstallprompt',{cancelable:true});failure.prompt=async()=>{throw Error('blocked')};events.dispatchEvent(failure);
 assert.equal((await store.triggerInstall()).outcome,'error');assert.equal(store.hasInstallPrompt(),false);
 events.dispatchEvent(event);events.dispatchEvent(new Event('appinstalled'));assert.equal(store.hasInstallPrompt(),false);
 let manual=0;events.addEventListener('hg:install-help',()=>manual++);store.openInstallHelp();assert.equal(manual,1);
 assert.ok(notices>=5);unsubscribe();delete global.window;
 console.log('PASS eager event capture, one-consumer prompt, retry event, error recovery, installed invalidation and manual help');
} finally {rmSync(out,{force:true});}
