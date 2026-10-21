"""Prepare the dev-only PM cookie selector without rebuilding a shared image."""
import copy
import hashlib
from pathlib import Path

ISSUER='https://keycloak.development.oanstaging.com/realms/staff'
MOUNT='/opt/oan/session-cookie-guard.cjs'


def configure(deployment):
    result=copy.deepcopy(deployment)
    name=result['metadata']['name']
    assert name.endswith('-pm-staff-portal-ui'), 'Not a Partner Management UI deployment'
    namespace=result['metadata'].get('namespace','commons')
    assert namespace=='commons', 'Guard is scoped to dev Commons'
    template=result['spec']['template']
    containers=template['spec']['containers']
    matches=[c for c in containers if any(e['name']=='KEYCLOAK_LOGOUT_URL' and
        e.get('value')==ISSUER+'/protocol/openid-connect/logout' for e in c.get('env',[]))]
    assert len(matches)==1, 'Expected one dev PM UI container'
    container=matches[0]
    source=Path(__file__).with_name('partner-session-cookie-guard.cjs').read_text(encoding='utf-8')
    digest=hashlib.sha256(source.encode()).hexdigest()
    cm_name=name.removesuffix('-staff-portal-ui')+'-session-cookie-guard'
    release=result['metadata'].get('labels',{}).get('app.kubernetes.io/instance',name.removesuffix('-pm-staff-portal-ui'))
    cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{
        'name':cm_name,'namespace':namespace,
        'labels':{'app.kubernetes.io/managed-by':'Helm','app.kubernetes.io/instance':release},
        'annotations':{'meta.helm.sh/release-name':release,'meta.helm.sh/release-namespace':namespace}},
        'data':{'session-cookie-guard.cjs':source}}
    env=container.setdefault('env',[])
    node_options=next((e for e in env if e['name']=='NODE_OPTIONS'),None)
    if node_options:
        assert 'valueFrom' not in node_options, 'Cannot append a referenced NODE_OPTIONS value'
        options=node_options.get('value','')
    else:
        node_options={'name':'NODE_OPTIONS','value':''};env.append(node_options);options=''
    preload='--require='+MOUNT
    if preload not in options.split():node_options['value']=(options+' '+preload).strip()
    for key,value in [('OAN_SESSION_COOKIE_GUARD','1'),('OAN_SESSION_EXPECTED_ISSUER',ISSUER)]:
        existing=next((e for e in env if e['name']==key),None)
        if existing:existing.clear();existing.update({'name':key,'value':value})
        else:env.append({'name':key,'value':value})
    volume={'name':'pm-session-cookie-guard','configMap':{'name':cm_name,'defaultMode':292}}
    volumes=template['spec'].setdefault('volumes',[])
    old=next((v for v in volumes if v['name']==volume['name']),None)
    if old:assert old==volume, 'Unexpected guard volume'
    else:volumes.append(volume)
    mount={'name':volume['name'],'mountPath':MOUNT,'subPath':'session-cookie-guard.cjs','readOnly':True}
    mounts=container.setdefault('volumeMounts',[])
    old=next((m for m in mounts if m['name']==mount['name']),None)
    if old:assert old==mount, 'Unexpected guard mount'
    else:mounts.append(mount)
    template.setdefault('metadata',{}).setdefault('annotations',{})['checksum/pm-session-cookie-guard']=digest
    return result,cm
