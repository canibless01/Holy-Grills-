"""Run explicitly against an isolated local Docker fixture, never Supabase."""
import concurrent.futures,json,subprocess,time,uuid
CONTAINER='hg-team-tests'
DB='teamtest4'
def sql(query):
    return subprocess.check_output(['docker','exec','-i',CONTAINER,'psql','-U','postgres','-d',DB,'-v','ON_ERROR_STOP=1','-Atq'],input=query,text=True).strip()
def lit(value):return "'"+value.replace("'","''")+"'"
def rpc(actor,action,data,request=None):
    return json.loads(sql(f"SELECT hg_team_workspace('{actor}','00000001-0000-0000-0000-000000000001',{lit(action)},{lit(json.dumps(data))}::jsonb,'{request or uuid.uuid4()}');"))
a='30000001-0000-0000-0000-000000000001';u='30000001-0000-0000-0000-000000000002'
sql(f"INSERT INTO profiles(id,campus_id,role,full_name) VALUES('{a}','00000001-0000-0000-0000-000000000001','admin','Local admin'),('{u}','00000001-0000-0000-0000-000000000001','student','Local designer');")
rid=sql("SELECT id FROM team_responsibilities WHERE campus_id='00000001-0000-0000-0000-000000000001' AND name='Designer';")
assert 'error' not in rpc(a,'member',{'profile_id':u,'responsibility_id':rid})
sql("UPDATE team_weeks SET due_at=now()+interval '1 day' WHERE campus_id='00000001-0000-0000-0000-000000000001';")
d=json.loads(sql(f"SELECT hg_team_workspace('{u}','00000001-0000-0000-0000-000000000001','snapshot');"));entry=next(x for x in d['entries'] if x['member_id']==d['member_id'])
values={'id':entry['id'],'version':entry['version'],'results':{t['id']:{'actual':t['target'],'evidence':'https://example.test/proof'} for t in entry['targets']},'narrative':{},'content':[]}
request=str(uuid.uuid4())
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda _:rpc(u,'save',values,request),range(6)))
assert all(r==results[0] for r in results) and results[0]['version']==2
assert sql(f"SELECT count(*) FROM team_audit WHERE actor_id='{u}' AND request_id='{request}';")=='1'
values['version']=2
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:rpc(u,'save',values),range(2)))
assert len([r for r in results if r.get('version')==3])==1 and len([r for r in results if r.get('error')=='stale'])==1
values['version']=3
sql(f"UPDATE team_weeks SET due_at=now()+interval '0.5 seconds' WHERE id='{entry['week_id']}';")
blocker=subprocess.Popen(['docker','exec','-i',CONTAINER,'psql','-U','postgres','-d',DB,'-Atq'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
blocker.stdin.write(f"BEGIN; SELECT id FROM team_entries WHERE id='{entry['id']}' FOR UPDATE; SELECT 'LOCKED'; SELECT pg_sleep(1); COMMIT;\n");blocker.stdin.close()
while blocker.stdout.readline().strip()!='LOCKED':pass
result=rpc(u,'save',values);blocker.wait(timeout=10)
assert result.get('error')=='closed',result
print('PASS six concurrent replays create one audited update; competing drafts reject one stale writer; a request waiting across the deadline is rejected.')
