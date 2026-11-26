import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const debug=process.argv.includes('--debug');
const release=process.argv.includes('--release');
if(debug&&release)throw Error('Choose a single build type');
const build=spawnSync(process.execPath,['node_modules/vite/bin/vite.js','build','--mode','android','--outDir','dist-android','--emptyOutDir'],
 {stdio:'inherit',env:{...process.env,NODE_ENV:debug?'development':'production'}});
if(build.status===0){const file='dist-android/index.html';writeFileSync(file,readFileSync(file,'utf8').replace('viewport-fit=cover','viewport-fit=contain'));}
process.exit(build.status??1);
