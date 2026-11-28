import {readFileSync,writeFileSync,copyFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {releasePlan} from './android-release-plan.mjs';
const {GITHUB_REPOSITORY:repo,GITHUB_SHA:sha,GITHUB_REF:ref,GH_TOKEN:token}=process.env;
if(ref!=='refs/heads/main'||!repo||!sha||!token)throw Error('Public Android publishing only runs in the authenticated main workflow');
const root=execFileSync('git',['rev-parse','--show-toplevel'],{encoding:'utf8'}).trim();
const remote=execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8'}).trim().split(/\s/)[0];
if(remote!==sha){console.log('A newer main commit exists; retaining this build as an artifact without changing the public download.');process.exit(0);}
const plan=releasePlan(JSON.parse(readFileSync('android-artifacts/package.json','utf8')),repo);
const apk='android-artifacts/'+plan.name,checksum=apk+'.sha256';
copyFileSync('android/app/build/outputs/apk/release/app-release.apk',apk);
writeFileSync(checksum,plan.manifest.sha256+'  '+plan.name+'\n');
writeFileSync('android-artifacts/release-notes.md','Holy Grills Android '+plan.manifest.version+'\n\nBuilt from main '+sha+'. Signed with the permanent Holy Grills app identity. Download the APK and open it to install or update. Existing app data stays with the same package and signing identity.\n');
execFileSync('gh',['release','create',plan.tag,apk,checksum,'--repo',repo,'--target',sha,'--title','Holy Grills Android '+plan.manifest.version,'--notes-file','android-artifacts/release-notes.md'],{stdio:'inherit'});
writeFileSync('public/android-release.json',JSON.stringify(plan.manifest,null,2)+'\n');
execFileSync('git',['config','user.name','github-actions[bot]'],{cwd:root});
execFileSync('git',['config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],{cwd:root});
execFileSync('git',['add','holy-grills-frontend/public/android-release.json'],{cwd:root});
execFileSync('git',['commit','-m','Publish Android '+plan.manifest.version+' download'],{cwd:root,stdio:'inherit'});
// Never force or rewrite newer work. A racing main update is handled by its own build.
execFileSync('git',['push','origin','HEAD:main'],{cwd:root,stdio:'inherit'});
console.log('Public APK and website download metadata published.');
