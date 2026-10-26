"""Offline SDK/auth/error tests and restored-data HTTP search; never production.
Real-server cases use captured vectors, so do NOT certify embedding/ranking quality.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from honcho import Honcho
CORE=Path('/home/hermes/hermes-fork-dev')
PLUGIN=Path('/home/hermes/hermes-phase2-dev/hermes-plugin-honcho')
sys.path.insert(0,str(CORE))
spec=importlib.util.spec_from_file_location('candidate_honcho',PLUGIN/'__init__.py',submodule_search_locations=[str(PLUGIN)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from candidate_honcho.session import HonchoSessionManager,HonchoSession,HonchoAuthError
from candidate_honcho import HonchoMemoryProvider, session as session_module

@pytest.fixture(autouse=True)
def isolated_client_factory(monkeypatch):
    monkeypatch.setattr(session_module, 'get_honcho_client', lambda config: config.client)

def manager(client):
    m=HonchoSessionManager()
    m._config=SimpleNamespace(client=client)
    m._cache['fixture']=HonchoSession('fixture','person','agent','current')
    return m

def mock_sdk(status=200):
    calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append((request.method,request.url.path,body))
        if request.url.path=='/v3/workspaces':return httpx.Response(200,json={'id':'fixture'})
        assert request.url.path=='/v3/workspaces/fixture/search'
        if status!=200:return httpx.Response(status,json={'detail':'controlled unavailable'})
        return httpx.Response(200,json=[{'id':'message1','workspace_id':'fixture','content':'recorded decision','peer_id':body['filters']['peer_id'],'session_id':'historic','created_at':'2026-01-01T00:00:00Z','metadata':{},'token_count':3}])
    client=Honcho(workspace_id='fixture',base_url='http://isolated.test',api_key='fixture',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return client,calls

@pytest.mark.parametrize('peer,expected',[('user','person'),('ai','agent'),('sibling','sibling')])
def test_real_sdk_request_author_and_no_peer_post(peer,expected):
    client,calls=mock_sdk();m=manager(client)
    assert 'recorded decision' in m.search_context('fixture','decision',peer=peer)
    assert [c[1] for c in calls]==['/v3/workspaces','/v3/workspaces/fixture/search']
    assert calls[-1][2]['filters']=={'peer_id':expected}


def test_search_backend_failure_not_empty_success():
    client,_=mock_sdk(503);m=manager(client)
    with pytest.raises(Exception):m.search_context('fixture','decision')


def test_search_tool_surfaces_backend_failure():
    client,_=mock_sdk(503);p=object.__new__(HonchoMemoryProvider)
    p._manager=manager(client);p._session_key='fixture'
    p._cron_skipped=False;p._session_initialized=True
    result=json.loads(p.handle_tool_call('honcho_search',{'query':'decision'}))
    assert 'error' in result and 'No relevant context found' not in str(result)


def test_rejected_static_auth_raises():
    client,_=mock_sdk(401);m=manager(client)
    with pytest.raises(HonchoAuthError):m.search_context('fixture','decision')


def test_auth_retry_uses_refreshed_client(monkeypatch):
    first,old=mock_sdk(401);second,new=mock_sdk();m=manager(first)
    refreshed=[]
    def refresh(**kwargs):m._config.client=second;refreshed.append(True);return True
    monkeypatch.setattr(m,'_force_reauth',refresh)
    assert 'recorded decision' in m.search_context('fixture','decision')
    assert refreshed==[True]
    assert len(old)==len(new)==2


def test_retry_auth_failure_remains_error(monkeypatch):
    first,_=mock_sdk(401);second,_=mock_sdk(401);m=manager(first)
    def refresh(**kwargs):m._config.client=second;return True
    monkeypatch.setattr(m,'_force_reauth',refresh)
    with pytest.raises(HonchoAuthError):m.search_context('fixture','decision')


def test_empty_search_is_no_match():
    c,_=mock_sdk();m=manager(c)
    assert m.search_context('fixture','')==''

FIXTURE_PATH=Path('/home/hermes/hermes-phase2-dev/rehearsal/private/history-fixtures.json')
@pytest.mark.parametrize('index',range(10))
@pytest.mark.skipif(os.environ.get("HERMES_RESTORED_TEST") != "1", reason="requires explicitly authorised network-isolated restore")
def test_restored_history_real_http_and_vectors(index):
    rows=json.loads(FIXTURE_PATH.read_text());f=rows[index]
    client=Honcho(workspace_id='hermes',base_url='http://127.0.0.1:8000',api_key='fixture',max_retries=0,timeout=15)
    results=client.search(f['query'],filters={'peer_id':f['peer_name']},limit=20)
    # Avoid disclosing source contents on assertion failure.
    assert any(r.id==f['public_id'] for r in results), 'historical target absent'
    assert all(r.peer_id==f['peer_name'] for r in results), 'cross-author result'
    m=manager(client);m._cache['fixture'].user_peer_id=f['peer_name']
    output=m.search_context('fixture',f['query'],max_tokens=2000)
    assert f['content'].strip()[:80] in output, 'manager omitted historical content'


@pytest.mark.skipif(os.environ.get("HERMES_RESTORED_TEST") != "1", reason="requires explicitly authorised network-isolated restore")
def test_unknown_author_real_http_no_results():
    client=Honcho(workspace_id='hermes',base_url='http://127.0.0.1:8000',api_key='fixture',max_retries=0,timeout=15)
    assert client.search('fixture-0',filters={'peer_id':'absent-test-peer'},limit=5)==[]
