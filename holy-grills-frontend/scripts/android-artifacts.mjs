import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const path=process.argv[2];if(!path||!existsSync(path))throw Error('Pass an existing APK path');
const sha=createHash('sha256').update(readFileSync(path)).digest('hex');
writeFileSync(path+'.sha256',sha+'  '+path.split('/').at(-1)+'\n');
const signer=process.env.APKSIGNER;
if(signer){
 const output=execFileSync(signer,['verify','--print-certs',path],{encoding:'utf8'});
 const aapt=process.env.AAPT;if(!aapt)throw Error('Set AAPT to read the actual package ID');
 const badging=execFileSync(aapt,['dump','badging',path],{encoding:'utf8'});
 const packageName=badging.match(/package: name='([^']+)'/)?.[1];if(!packageName)throw Error('Cannot read APK package ID');
 const fingerprint=output.match(/certificate SHA-256 digest: ([a-f0-9]+)/i)?.[1];
 if(!fingerprint)throw Error('No signing certificate found');
 const formattedFingerprint=fingerprint.match(/../g).join(':').toUpperCase();
 if(packageName==='com.holygrills.app'){
   const identity=JSON.parse(readFileSync('public/.well-known/assetlinks.json','utf8'));
   if(!identity.some(row=>row.target?.package_name===packageName&&row.target?.sha256_cert_fingerprints?.includes(formattedFingerprint)))throw Error('Release signing certificate does not match the permanent app identity. Check the signing secrets; do not publish this APK.');
 }

 mkdirSync('android-artifacts',{recursive:true});
 const version=badging.match(/versionName='([^']+)'/)?.[1],versionCode=Number(badging.match(/versionCode='(\d+)'/)?.[1]);
 if(!version||!Number.isInteger(versionCode)||versionCode<1)throw Error('Cannot read APK version');
 writeFileSync('android-artifacts/package.json',JSON.stringify({packageName,version,versionCode,sha256:sha},null,2)+'\n');
 writeFileSync('android-artifacts/assetlinks.json',JSON.stringify([{relation:['delegate_permission/common.handle_all_urls'],target:{namespace:'android_app',package_name:packageName,sha256_cert_fingerprints:[formattedFingerprint]}}],null,2)+'\n');
}
console.log('APK checksum written. App-links association generated only from a verified signing certificate.');
