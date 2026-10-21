#!/usr/bin/env python3
"""Compatibility renderer for the exact installed legacy dev charts.

Use with Helm --post-renderer during this migration. New chart dev.4 defaults
already select the shared gateway. Private/test hosts retain their gateways.
The PM UI also receives the dev session-cookie guard; ship its sibling files.
"""
import base64
import copy
import json
import re
import sys
import yaml
from partner_session_guard import configure as configure_partner_session_guard

DOMAIN='development.oanstaging.com'
GATEWAY='istio-system/development'
ALIASES={
 'minio-api.commons-dev.oanstaging.com':'minio-farmer.'+DOMAIN,
 'keycloak.commons-dev.oanstaging.com':'keycloak.'+DOMAIN,
 'odk.commons-dev.oanstaging.com':'odk-central.'+DOMAIN,
 'farmer-dev.oanstaging.com':'farmer-registry.'+DOMAIN,
 'staff-iam.commons-dev.oanstaging.com':'staff-iam.'+DOMAIN,
}


def text(value):
    value=re.sub(r'(?<![a-zA-Z0-9_.-])([a-z0-9-]+)-development\.oanstaging\.com(?![a-zA-Z0-9_.-])',lambda m:m[1]+'.'+DOMAIN,value)
    for old,new in ALIASES.items():value=value.replace(old,new)
    return value


def transform(obj):
    if isinstance(obj,dict):
        obj={k:transform(v) for k,v in obj.items()}
        if str(obj.get('name') or '').upper().endswith('COOKIE_DOMAIN') and obj.get('value')=='.oanstaging.com':obj['value']='.'+DOMAIN
        if obj.get('kind')=='VirtualService' and any(h.endswith('.'+DOMAIN) for h in obj['spec'].get('hosts',[])):
            assert all(h.endswith('.'+DOMAIN) for h in obj['spec']['hosts']), 'Mixed private/public hosts require separate routes'
            obj['spec']['gateways']=[GATEWAY]
        if obj.get('kind')=='Secret':
            for key,value in (obj.get('data') or {}).items():
                try:
                    decoded=base64.b64decode(value,validate=True).decode('utf-8')
                except (ValueError,UnicodeDecodeError):continue
                changed=text(decoded)
                if changed!=decoded:obj['data'][key]=base64.b64encode(changed.encode()).decode()
        return obj
    if isinstance(obj,list):return [transform(v) for v in obj]
    return text(obj) if isinstance(obj,str) else obj


def main():
    documents=[transform(d) for d in yaml.safe_load_all(sys.stdin) if d]
    guard_maps=[]
    for index,document in enumerate(documents):
        if document.get('kind')=='Deployment' and document['metadata']['name'].endswith('-pm-staff-portal-ui'):
            documents[index],config=configure_partner_session_guard(document)
            guard_maps.append(config)
    for config in guard_maps:
        matches=[d for d in documents if d.get('kind')=='ConfigMap' and d['metadata']['name']==config['metadata']['name']]
        if matches:
            assert len(matches)==1 and matches[0]['data']==config['data'], 'Conflicting session guard ConfigMap'
        else:documents.append(config)
    if '--skip-initialization-jobs' in sys.argv:
        documents=[d for d in documents if d['kind']!='Job']
    # No logs: Helm consumes stdout as the complete manifest.
    yaml.safe_dump_all(documents,sys.stdout,sort_keys=False,width=100)


if __name__=='__main__':main()
