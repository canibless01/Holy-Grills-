import { existsSync } from 'node:fs';
const required=['ANDROID_KEYSTORE_PATH','ANDROID_KEYSTORE_PASSWORD','ANDROID_KEY_ALIAS','ANDROID_KEY_PASSWORD','VITE_GOOGLE_MAPS_API_KEY'];
const missing=required.filter(key=>!process.env[key]);
if(missing.length)throw Error('Release setup missing: '+missing.join(', ')+'. Do not distribute a debug or unsigned APK as a customer release.');
if(!existsSync(process.env.ANDROID_KEYSTORE_PATH))throw Error('Signing keystore file not found');
console.log('Signing inputs and native Maps key are configured; no credential values printed.');
