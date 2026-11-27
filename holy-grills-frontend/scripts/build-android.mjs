import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { loadEnv } from 'vite';
const debug=process.argv.includes('--debug');
const release=process.argv.includes('--release');
if(debug&&release)throw Error('Choose a single build type');
const mapsKey=process.env.VITE_GOOGLE_MAPS_API_KEY || loadEnv('android',process.cwd(),'VITE_').VITE_GOOGLE_MAPS_API_KEY;
if(!mapsKey)throw Error('Android build needs VITE_GOOGLE_MAPS_API_KEY (GitHub Actions: HG_ANDROID_GOOGLE_MAPS_API_KEY). No keyless APK will be produced.');
const build=spawnSync(process.execPath,['node_modules/vite/bin/vite.js','build','--mode','android','--outDir','dist-android','--emptyOutDir'],
 {stdio:'inherit',env:{...process.env,NODE_ENV:debug?'development':'production'}});
if(build.status===0){const file='dist-android/index.html';writeFileSync(file,readFileSync(file,'utf8').replace('viewport-fit=cover','viewport-fit=contain'));}
process.exit(build.status??1);
