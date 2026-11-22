#!/usr/bin/env python3
"""Read-only, schema-only PostgreSQL architecture export. Never exports data or applies SQL.
Requires psycopg2 (available in the backend environment), and pg_dump 17+ or Docker.
Credentials are passed through environment variables, never shell arguments/logs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlparse
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
MANAGED = {'auth','storage','extensions','graphql','graphql_public','realtime','net','vault','cron','supabase_migrations','supabase_functions','pgbouncer','pgsodium','pgsodium_masks'}


def connection_environment(url):
    p=urlparse(url)
    if p.scheme not in ('postgres','postgresql') or not p.hostname or not p.username:
        raise ValueError('Use a PostgreSQL session-pooler or direct connection URL.')
    query=parse_qs(p.query)
    sslmode=query.get('sslmode',['require'])[0]
    if p.hostname not in ('localhost','127.0.0.1','::1') and sslmode not in ('require','verify-ca','verify-full'):
        raise ValueError('Remote database exports require encrypted PostgreSQL connections.')
    return {'PGHOST':p.hostname,'PGPORT':str(p.port or 5432),'PGUSER':unquote(p.username),
            'PGPASSWORD':unquote(p.password or ''),'PGDATABASE':unquote(p.path.lstrip('/') or 'postgres'),
            'PGSSLMODE':sslmode,
            'PGCONNECT_TIMEOUT':'15','PGOPTIONS':'-c default_transaction_read_only=on'}


def safe_run_dump(env, schemas, destination, docker_image='postgres:17-alpine', snapshot=None):
    args=['--schema-only','--no-owner','--no-tablespaces','--no-publications','--lock-wait-timeout=10s']
    if snapshot:args.extend(['--snapshot',snapshot])
    for schema in schemas:args.extend(['--schema',schema])
    binary=shutil.which('pg_dump')
    if binary:
        command=[binary,*args]
    elif shutil.which('docker'):
        command=['docker','run','--rm','--network','host']
        for name in env:command.extend(['--env',name])
        command.extend([docker_image,'pg_dump',*args])
    else:
        raise RuntimeError('Install PostgreSQL 17+ client tools or Docker before exporting.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Atomic publication: a failed dump cannot leave a seemingly valid schema.sql.
    temporary=destination.with_suffix(destination.suffix+'.partial')
    try:
        with temporary.open('wb') as out:
            proc=subprocess.run(command,env={**os.environ,**env},stdout=out,stderr=subprocess.PIPE)
        if proc.returncode:
            raise RuntimeError('pg_dump failed; check database connectivity, credentials and pg_dump/server versions. No completed SQL was published.')
        os.chmod(temporary,0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def normalize_application_sql(text):
    # Only pg_dump's first SCHEMA public section, before any function bodies.
    marker='--\n-- Name: public; Type: SCHEMA; Schema: -; Owner: -\n--\n\nCREATE SCHEMA public;'
    return text.replace(marker,marker.replace('CREATE SCHEMA public;','CREATE SCHEMA IF NOT EXISTS public;'),1)


def quote(value):return '"'+value.replace('"','""')+'"'


def managed_overlays(inventory):
    """Only app-owned auth/storage hooks and policies; never replace managed tables."""
    statements=['-- Apply after application.sql on a fresh Supabase project only.']
    for trigger in inventory['triggers']:
        if trigger['schema'] not in ('auth','storage'):continue
        relation=quote(trigger['schema'])+'.'+quote(trigger['table'])
        statements.extend([f'DROP TRIGGER IF EXISTS {quote(trigger["name"])} ON {relation};',trigger['definition']+';'])
        mode={'D':'DISABLE','R':'ENABLE REPLICA','A':'ENABLE ALWAYS'}.get(trigger['enabled'])
        if mode:statements.append(f'ALTER TABLE {relation} {mode} TRIGGER {quote(trigger["name"])};')
    for policy in inventory['policies']:
        if policy['schemaname'] not in ('auth','storage'):continue
        relation=quote(policy['schemaname'])+'.'+quote(policy['tablename'])
        roles=', '.join('PUBLIC' if r=='public' else quote(r) for r in policy['roles'])
        statement=f'CREATE POLICY {quote(policy["policyname"])} ON {relation} AS {policy["permissive"]} FOR {policy["cmd"]} TO {roles}'
        if policy['qual']:statement+=' USING ('+policy['qual']+')'
        if policy['with_check']:statement+=' WITH CHECK ('+policy['with_check']+')'
        statements.extend([f'DROP POLICY IF EXISTS {quote(policy["policyname"])} ON {relation};',statement+';'])
    return '\n\n'.join(statements)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--url-env',default='SOURCE_DATABASE_URL',help='Name of the environment variable, not the URL itself.')
    parser.add_argument('--docker-image',default='postgres:17-alpine')
    args=parser.parse_args()
    url=os.environ.get(args.url_env)
    if not url:parser.error('Set '+args.url_env+' securely; do not put credentials in the command.')
    if args.output.exists() and any(args.output.iterdir()):parser.error('Use a new empty output directory to preserve previous snapshots.')
    env=connection_environment(url)
    kwargs={k:v for k,v in {'host':env['PGHOST'],'port':env['PGPORT'],'user':env['PGUSER'],'password':env['PGPASSWORD'],'dbname':env['PGDATABASE'],'sslmode':env['PGSSLMODE'],'connect_timeout':15}.items()}
    try:
        with psycopg2.connect(**kwargs) as conn:
            conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
            with conn.cursor() as cursor:
                cursor.execute((ROOT/'tools/schema_architecture_inventory.sql').read_text())
                inventory=cursor.fetchone()[0]
                cursor.execute("select to_regclass('cron.job')")
                if cursor.fetchone()[0]:
                    cursor.execute('select jobname,schedule,command,active from cron.job order by jobid')
                    inventory['database_cron_jobs']=[dict(zip(('name','schedule','command','active'),row)) for row in cursor.fetchall()]
                else:inventory['database_cron_jobs']=[]
                cursor.execute("select rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls from pg_roles where rolname not like 'pg_%' order by rolname")
                inventory['role_attributes']=[dict(zip(('name','superuser','inherit','create_role','create_db','login','replication','bypass_rls'),row)) for row in cursor.fetchall()]
                cursor.execute('select r.rolname,m.rolname,g.rolname,a.admin_option,a.inherit_option,a.set_option from pg_auth_members a join pg_roles r on r.oid=a.roleid join pg_roles m on m.oid=a.member join pg_roles g on g.oid=a.grantor order by r.rolname,m.rolname')
                inventory['role_memberships']=[dict(zip(('role','member','grantor','admin_option','inherit_option','set_option'),row)) for row in cursor.fetchall()]
                cursor.execute('select pg_export_snapshot()')
                snapshot=cursor.fetchone()[0]
                schemas=inventory['application_schemas'] or []
                if not schemas:raise RuntimeError('No application schemas found.')
                reference_schemas=[*schemas,*sorted(MANAGED-{'pgbouncer'})]
                cursor.execute('select nspname from pg_namespace where nspname=any(%s)',(reference_schemas,))
                actual=[r[0] for r in cursor.fetchall()]
                args.output.mkdir(parents=True,exist_ok=True)
                os.chmod(args.output,0o700)
                # The exporter transaction stays open: both pg_dump sessions import
                # its snapshot, instead of independently racing another chat's DDL.
                safe_run_dump(env,schemas,args.output/'application.sql',args.docker_image,snapshot)
                safe_run_dump(env,actual,args.output/'reference/full-database.schema.sql',args.docker_image,snapshot)
        raw=(args.output/'application.sql').read_text()
        (args.output/'reference/application.raw.sql').write_text(raw)
        (args.output/'application.sql').write_text(normalize_application_sql(raw))
        (args.output/'managed-overlays.sql').write_text(managed_overlays(inventory))
        (args.output/'inventory.json').write_text(json.dumps(inventory,indent=2,default=str)+'\n')
        manifest={'schema_only':True,'table_rows_exported':False,'captured_at':str(inventory['captured_at']),
                  'application_schemas':schemas,'counts':{k:len(inventory.get(k) or []) for k in ('relations','functions','types','constraints','indexes','views','triggers','policies')},
                  'restore_tested':False,'public_schema_creation':'IF NOT EXISTS for fresh Supabase public schema; canonical dump retained in reference/application.raw.sql','hashes':{str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.rglob('*')) if p.is_file()}}
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        for path in args.output.rglob('*'):
            if path.is_file():os.chmod(path,0o600)
        print(json.dumps({'exported':True,'output':str(args.output),'counts':manifest['counts'],'restore_tested':False}))
    except Exception as exc:
        # libpq errors may contain credential fragments when URLs are malformed.
        print('Export did not complete ('+type(exc).__name__+'). No database changes were made.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':sys.exit(main())
