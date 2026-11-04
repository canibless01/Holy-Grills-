import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from flask import Flask,g
from app import create_app
from app.config import Config
from app.tasks.celery_app import ContextTask


def test_background_context_has_config_without_http_routes():
    app=create_app(background=True)
    assert app.config['SECRET_KEY']
    assert not any(rule.rule.startswith('/api') for rule in app.url_map.iter_rules())


def test_background_keeps_production_secret_validation():
    class Unsafe(Config):
        SECRET_KEY='change-me-in-production'
        JWT_SECRET='change-me-in-production'
        DEBUG=False
        TESTING=False
    with pytest.raises(RuntimeError): create_app(Unsafe,background=True)


def test_each_task_has_isolated_flask_g_state():
    seen=[]
    def run():
        seen.append(getattr(g,'marker',None));g.marker='task-private';return 'ok'
    task=SimpleNamespace(run=run)
    with patch('app.tasks.celery_app._worker_flask_app',return_value=Flask(__name__)):
        assert ContextTask.__call__(task)=='ok'
        assert ContextTask.__call__(task)=='ok'
    assert seen==[None,None]


def test_scheduler_import_does_not_load_web_routes_or_swagger():
    script="from app.tasks.celery_app import celery_app; celery_app.loader.import_default_modules(); import sys; assert 'app.routes.admin' not in sys.modules; assert 'flasgger' not in sys.modules; assert 'app.tasks.scheduled' in sys.modules"
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env={**os.environ,'PYTHONPATH':os.path.dirname(os.path.dirname(__file__))})
    assert result.returncode==0,result.stderr
