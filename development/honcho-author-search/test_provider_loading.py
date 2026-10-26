"""Actual external-provider discovery/config resolution using protected copies; no live calls."""
import json,os,shutil,sys
from pathlib import Path
import pytest
sys.path.insert(0,'/home/hermes/hermes-fork-dev')
ROOT=Path('/home/hermes/hermes-phase2-dev')

@pytest.mark.parametrize('profile,host',[('default','hermes'),('homelab','hermes_homelab')])
def test_actual_loader_and_existing_honcho_identity(tmp_path,monkeypatch,profile,host):
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    home=tmp_path/'.hermes'
    active=home if profile=='default' else home/'profiles'/profile
    active.mkdir(parents=True)
    (active/'config.yaml').write_text('memory:\n  provider: honcho\n')
    target=active/'plugins'/'honcho'
    shutil.copytree(ROOT/'hermes-plugin-honcho',target,ignore=shutil.ignore_patterns('__pycache__'))
    raw=json.loads((ROOT/'rehearsal/private/profiles/default/honcho.json').read_text())
    (home/'honcho.json').write_text(json.dumps(raw))
    monkeypatch.setenv('HOME',str(tmp_path));monkeypatch.setenv('HERMES_HOME',str(active))
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    token=set_hermes_home_override(active)
    try:
        from plugins.memory import load_memory_provider,import_provider_module,find_provider_dir
        provider=load_memory_provider('honcho')
        assert provider is not None,'external provider failed to load'
        assert find_provider_dir('honcho')==target
        client_module=import_provider_module('honcho','client')
        assert client_module.resolve_active_host()==host,'profile selected different host identity'
        config=client_module.HonchoClientConfig.from_global_config()
        expected=raw['hosts'][host]
        assert config.workspace_id==expected.get('workspace',raw.get('workspace',host)),'workspace identity changed'
        assert config.peer_name==expected.get('peerName','user'),'human identity changed'
        assert config.ai_peer==expected.get('aiPeer',host),'assistant identity changed'
        assert config.base_url==expected.get('baseUrl',raw.get('baseUrl')),'endpoint changed'
    finally:reset_hermes_home_override(token)
