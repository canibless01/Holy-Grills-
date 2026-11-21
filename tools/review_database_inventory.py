"""Render a metadata-only snapshot into reviewable CSVs and structural findings.

The SQL companion is read-only. This report never treats a matched expression,
source mention or passed structural check as end-to-end authorization proof.
"""
import argparse,collections,csv,json,re
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('snapshot',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
x=json.loads(args.snapshot.read_text());args.output.mkdir(parents=True,exist_ok=True)
def write(name,rows,columns=None):
 if not rows:return
 columns=columns or list(rows[0])
 with (args.output/name).open('w',newline='') as out:
  w=csv.DictWriter(out,fieldnames=columns,extrasaction='ignore',lineterminator='\n');w.writeheader()
  for row in rows:w.writerow({key:json.dumps(value,sort_keys=True) if isinstance(value,(list,dict)) else value for key,value in row.items()})
for name in ('policies','tables','views','triggers','indexes','functions','migrations','extensions','flags'):write(name+'.csv',x[name])
violations=[]
for t in x['tables']:
 if not t['rls']:violations.append('RLS disabled: '+t['schema']+'.'+t['name'])
 if t['schema']=='hg_internal' and any(t[role][priv] for role in ('anon','authenticated') for priv in t[role]):violations.append('Private browser grant: '+t['name'])
for view in x['views']:
 if view['authenticated'] and 'security_invoker=true' not in (view['options'] or []):violations.append('Non-invoker readable view: '+view['name'])
for index in x['indexes']:
 if not index['valid']:violations.append('Invalid index: '+index['name'])
def groups(rows,key):
 d=collections.defaultdict(list)
 for row in rows:d[key(row)].append(row)
 return [group for group in d.values() if len(group)>1]
triggers=groups(x['triggers'],lambda t:re.sub(r'^CREATE (CONSTRAINT )?TRIGGER \S+ ',r'CREATE \1TRIGGER ',t['definition']))
policies=groups(x['policies'],lambda p:tuple(str(p[k]) for k in ('schemaname','tablename','permissive','roles','cmd','qual','with_check')))
indexes=groups(x['indexes'],lambda i:re.sub(r'^CREATE (UNIQUE )?INDEX \S+ ON ',r'CREATE \1INDEX ON ',i['definition']))
overloads=groups(x['functions'],lambda f:(f['schema'],f['name']))
summary={'captured_at':x.get('captured_at'),'counts':{k:len(v) for k,v in x.items() if isinstance(v,list)},'structural_findings':violations,
 'duplicate_policy_groups':[[r['policyname'] for r in g] for g in policies], 'duplicate_trigger_groups':[[r['name'] for r in g] for g in triggers],
 'identical_index_groups':[[r['name'] for r in g] for g in indexes], 'overloads':[[r['signature'] for r in g] for g in overloads],
 'browser_definers':[r['signature'] for r in x['functions'] if r['definer'] and (r['anon'] or r['authenticated'])],
 'browser_invokers':[r['signature'] for r in x['functions'] if not r['definer'] and (r['anon'] or r['authenticated'])]}
(args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'counts':summary['counts'],'structural_findings':violations,'duplicates':{'policies':len(policies),'triggers':len(triggers),'indexes':len(indexes)},'overload_groups':len(overloads)},indent=2))
