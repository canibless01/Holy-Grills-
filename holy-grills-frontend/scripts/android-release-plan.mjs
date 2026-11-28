/** A release pointer is built from verified APK metadata, never guessed version fields. */
export function releasePlan(metadata, repo) {
  if(metadata.packageName!=='com.holygrills.app'||!/^\d+\.\d+\.\d+(?:\+\d+(?:\.\d+)?)?$/.test(metadata.version)||!Number.isInteger(metadata.versionCode)||metadata.versionCode<1||!/^[a-f0-9]{64}$/i.test(metadata.sha256))throw Error('Invalid verified release metadata');
  if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo))throw Error('Invalid release repository');
  const label=metadata.version.replace('+','-build-');
  const tag='android-v'+label,name='Holy-Grills-'+label+'.apk';
  return {tag,name,manifest:{available:true,version:metadata.version,versionCode:metadata.versionCode,url:`https://github.com/${repo}/releases/download/${tag}/${name}`,sha256:metadata.sha256}};
}
