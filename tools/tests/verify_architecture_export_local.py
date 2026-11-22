"""Opt-in disposable PostgreSQL pg_dump -> empty restore proof; no remote DB accepted.
Run with ARCHITECTURE_TEST_ADMIN_URL pointing to a dedicated local Postgres 17 container.
No production connection variables are used. Created database names are random.
"""
import os,subprocess,json,psycopg2,tempfile,uuid,sys
from urllib.parse import urlparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];out=Path(tempfile.mkdtemp(prefix='hg-schema-proof-'))/'export'
url=os.environ['ARCHITECTURE_TEST_ADMIN_URL'];assert urlparse(url).hostname in ('127.0.0.1','localhost'), 'Disposable localhost only'
BASE=psycopg2.extensions.parse_dsn(url);BASE.pop('dbname',None)
source='arch_source_'+uuid.uuid4().hex;target='arch_target_'+uuid.uuid4().hex
c=psycopg2.connect(dbname='postgres',**BASE);c.autocommit=True
with c.cursor() as q:
 for role in ('anon','authenticated','service_role'):q.execute("DO $$ BEGIN CREATE ROLE "+role+"; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
 for name in (source,target):q.execute('CREATE DATABASE '+name)
c.close()
platform='''CREATE SCHEMA auth;CREATE TABLE auth.users(id uuid PRIMARY KEY);CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$SELECT NULL::uuid$$; CREATE SCHEMA storage;CREATE TABLE storage.objects(id uuid PRIMARY KEY,owner_id text);ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;'''
with psycopg2.connect(dbname=source,**BASE) as c:
 with c.cursor() as q:
  q.execute(platform)
  q.execute('''CREATE SCHEMA hg_internal;CREATE TYPE public.arch_status AS ENUM ('pending','paid');
  CREATE TABLE public.profiles(id uuid PRIMARY KEY REFERENCES auth.users(id), email text);
  CREATE TABLE public.menu_items(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,price numeric(12,2) NOT NULL CHECK(price>=0),status public.arch_status DEFAULT 'pending');
  CREATE INDEX menu_status_index ON public.menu_items(status);
  ALTER TABLE public.menu_items ENABLE ROW LEVEL SECURITY;
  CREATE POLICY menu_read ON public.menu_items FOR SELECT TO anon USING(true);
  GRANT USAGE ON SCHEMA public TO anon; GRANT SELECT ON public.menu_items TO anon;
  CREATE FUNCTION hg_internal.private_value() RETURNS integer LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$SELECT 7$$;
  REVOKE ALL ON FUNCTION hg_internal.private_value() FROM PUBLIC,anon,authenticated;GRANT EXECUTE ON FUNCTION hg_internal.private_value() TO service_role;
  CREATE FUNCTION public.on_signup() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.profiles(id) VALUES(NEW.id); RETURN NEW;END$$;
  CREATE TRIGGER source_signup AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.on_signup();
  CREATE POLICY own_upload ON storage.objects FOR SELECT TO authenticated USING(owner_id=auth.uid()::text);
  CREATE VIEW public.menu_public WITH(security_invoker=true) AS SELECT id,price FROM public.menu_items;
  INSERT INTO public.menu_items(price) VALUES(987654321.12);
  INSERT INTO auth.users(id) VALUES('11111111-1111-4111-8111-111111111111');
  UPDATE public.profiles SET email='PRIVATE_CUSTOMER_SENTINEL@example.invalid';''')
env={**os.environ,'ARCH_TEST_SOURCE_URL':url.rsplit('/',1)[0]+'/'+source+'?sslmode=disable'}
command=[sys.executable,str(ROOT/'tools/export_database_architecture.py'),'--url-env','ARCH_TEST_SOURCE_URL','--output',str(out)]
if os.environ.get('ARCHITECTURE_TEST_BROWSER_WRAPPER')=='1':
 env.update(SOURCE_DATABASE_URL=env['ARCH_TEST_SOURCE_URL'],HG_SCHEMA_EXPORT_PYTHON=sys.executable)
 command=['bash',str(ROOT/'tools/export_schema_browser_terminal.sh'),str(out)]
r=subprocess.run(command,env=env,capture_output=True,text=True)
assert r.returncode==0,(r.stdout,r.stderr)
text=(out/'application.sql').read_text()
assert 'PRIVATE_CUSTOMER_SENTINEL' not in text and '987654321.12' not in text
assert 'CREATE TABLE' in text and 'CREATE POLICY menu_read' in text and 'ENABLE ROW LEVEL SECURITY' in text
assert 'security_invoker' in text and 'REVOKE ALL ON FUNCTION hg_internal.private_value() FROM PUBLIC' in text
with psycopg2.connect(dbname=target,**BASE) as c:
 with c.cursor() as q:q.execute(platform)
for filename in ('application.sql','managed-overlays.sql'):
 command=['docker','run','--rm','--network','host','-e','PGPASSWORD','-v',str(out)+':/export:ro','postgres:17-alpine','psql','-h','127.0.0.1','-p',str(BASE.get('port',5432)),'-U',BASE.get('user','postgres'),'-d',target,'--single-transaction','--set','ON_ERROR_STOP=1','--file','/export/'+filename]
 result=subprocess.run(command,env={**os.environ,'PGPASSWORD':BASE.get('password','')},capture_output=True,text=True)
 assert result.returncode==0,result.stderr[-1000:]
with psycopg2.connect(dbname=target,**BASE) as c:
 with c.cursor() as q:
  q.execute('select count(*) from public.menu_items');assert q.fetchone()[0]==0
  q.execute("select relrowsecurity from pg_class where oid='public.menu_items'::regclass");assert q.fetchone()[0]
  q.execute("select has_function_privilege('anon','hg_internal.private_value()','EXECUTE'),has_function_privilege('service_role','hg_internal.private_value()','EXECUTE')");assert q.fetchone()==(False,True)
  q.execute("select count(*) from pg_policies where schemaname='storage' and policyname='own_upload'");assert q.fetchone()[0]==1
  q.execute("INSERT INTO auth.users(id) VALUES('22222222-2222-4222-8222-222222222222')")
  q.execute('select count(*) from public.profiles');assert q.fetchone()[0]==1
print(json.dumps({'real_pg_dump_and_restore':True,'rows_copied':0,'enums_indexes_views_rls_acl_preserved':True,'auth_hook_and_storage_policy_restored':True,'source_data_unchanged':True}))

c=psycopg2.connect(dbname='postgres',**BASE);c.autocommit=True
with c.cursor() as q:
 for name in (source,target):q.execute('DROP DATABASE '+name+' WITH(FORCE)')
c.close()
