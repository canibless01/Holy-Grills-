"""Exporter safeguards; a real local pg_dump/restore proof is run separately."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('architecture_export',ROOT/'tools/export_database_architecture.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_url_special_characters_do_not_enter_command_arguments():
 env=module.connection_environment('postgresql://postgres.project:a%40b%3Ac@pooler.example:5432/postgres?sslmode=verify-full')
 assert env['PGPASSWORD']=='a@b:c' and env['PGHOST']=='pooler.example'
 assert env['PGSSLMODE']=='verify-full' and 'read_only=on' in env['PGOPTIONS']


def test_failed_dump_never_publishes_completed_sql(tmp_path):
 output=tmp_path/'schema.sql'
 class Result:returncode=1;stderr=b'private provider error'
 with patch.object(module.shutil,'which',return_value='/usr/bin/pg_dump'),patch.object(module.subprocess,'run',return_value=Result()) as run,pytest.raises(RuntimeError):
  module.safe_run_dump({'PGPASSWORD':'not-for-arguments'},['public','hg_internal'],output,snapshot='snapshot-token')
 assert not output.exists() and not output.with_suffix('.sql.partial').exists()
 args=run.call_args.args[0]
 assert '--schema-only' in args and '--snapshot' in args and 'not-for-arguments' not in args
 assert '--data-only' not in args


def test_managed_overlay_keeps_only_custom_hooks_and_policies():
 inv={'triggers':[{'schema':'auth','table':'users','name':'signup','enabled':'A','definition':'CREATE TRIGGER signup AFTER INSERT ON auth.users EXECUTE FUNCTION public.signup()'},{'schema':'public','table':'orders','name':'not-overlay'}],
 'policies':[{'schemaname':'storage','tablename':'objects','policyname':'read own','permissive':'PERMISSIVE','cmd':'SELECT','roles':['authenticated'],'qual':'owner_id = auth.uid()::text','with_check':None}]}
 sql=module.managed_overlays(inv)
 assert 'ENABLE ALWAYS TRIGGER "signup"' in sql and 'TO "authenticated"' in sql
 assert 'not-overlay' not in sql and 'CREATE TABLE' not in sql
 assert 'DROP TABLE' not in sql and 'INSERT INTO' not in sql


def test_public_schema_normalization_preserves_reference_code():
 marker='--\n-- Name: public; Type: SCHEMA; Schema: -; Owner: -\n--\n\nCREATE SCHEMA public;'
 text=marker+'\nCREATE FUNCTION test() RETURNS void AS $$BEGIN CREATE SCHEMA public; END$$ LANGUAGE plpgsql;'
 result=module.normalize_application_sql(text)
 assert 'CREATE SCHEMA IF NOT EXISTS public;' in result
 assert 'BEGIN CREATE SCHEMA public; END' in result


def test_remote_credentials_never_use_plaintext_database_transport():
 with pytest.raises(ValueError):module.connection_environment('postgresql://postgres:secret@remote.example/postgres?sslmode=disable')
 assert module.connection_environment('postgresql://postgres:secret@localhost/postgres?sslmode=disable')['PGSSLMODE']=='disable'
