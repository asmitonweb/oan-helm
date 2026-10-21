"""Generate temporary legacy DNS/ingress compatibility from sanitized inventory.

Creates local files only. Apply environment-owned ingress after review; restore
only the DNS records captured for this dev server. No chart ownership changes.
"""
import argparse
import copy
import json
from pathlib import Path
import yaml

DOMAIN='development.oanstaging.com'
LEGACY_GATEWAY='istio-system/development-legacy'


def canonical(host):
    overrides={
        'keycloak-crop-development.oanstaging.com':'keycloak.'+DOMAIN,
        'keycloak-livestock-development.oanstaging.com':'keycloak.'+DOMAIN,
        'staff-iam-crop-development.oanstaging.com':'staff-iam.'+DOMAIN,
        'staff-iam-livestock-development.oanstaging.com':'staff-iam.'+DOMAIN,
    }
    return overrides.get(host,host.removesuffix('-development.oanstaging.com')+'.'+DOMAIN)


def build_routes(host_map, routes):
    host_map=dict(host_map)
    # Cached Enketo surveys also reference this older Commons URL. Its existing
    # Nginx wildcard proxies the original Host; it needs an Istio alias, not a
    # browser redirect or a new certificate/server block.
    odk_host='odk-central.'+DOMAIN
    if any(odk_host in route['spec'].get('hosts',[]) for route in routes):
        host_map['odk.commons-dev.oanstaging.com']=odk_host
    documents=[{'apiVersion':'networking.istio.io/v1beta1','kind':'Gateway',
        'metadata':{'name':'development-legacy','namespace':'istio-system','labels':{'app.kubernetes.io/part-of':'oan-development-legacy-compatibility','app.kubernetes.io/managed-by':'oan-environment-operations'}},
        'spec':{'selector':{'istio':'ingressgateway'},'servers':[{'port':{'number':8080,'name':'legacy-development-http','protocol':'HTTP'},'hosts':sorted(host_map)}]}}]
    matched=set()
    for route in routes:
        aliases=[old for old,new in host_map.items() if new in route['spec'].get('hosts',[])]
        if not aliases:continue
        matched.update(aliases)
        spec=copy.deepcopy(route['spec']);spec['hosts']=sorted(aliases);spec['gateways']=[LEGACY_GATEWAY]
        documents.append({'apiVersion':'networking.istio.io/v1beta1','kind':'VirtualService',
            'metadata':{'name':'legacy-'+route['metadata']['name'],'namespace':route['metadata']['namespace'],
                        'labels':{'app.kubernetes.io/part-of':'oan-development-legacy-compatibility','app.kubernetes.io/managed-by':'oan-environment-operations'},
                        'annotations':{'oan.org/canonical-route':route['metadata']['namespace']+'/'+route['metadata']['name']}},'spec':spec})
    assert matched==set(host_map), 'No canonical route for legacy hosts: '+','.join(sorted(set(host_map)-matched))
    return documents


def build_nginx(host_map, certificates):
    text='# Temporary old-URL compatibility. Remove only after explicit completion.\nmap_hash_bucket_size 128;\n'
    text+='map $host $oan_legacy_canonical {\n    default "";\n'
    for old,new in sorted(host_map.items()):text+='    '+old+' '+new+';\n'
    text+='}\nmap $http_accept $oan_legacy_html { default 0; ~*text/html 1; }\n'
    text+='map $host $oan_legacy_object_api { default 0; minio-farmer-development.oanstaging.com 1; }\n'
    text+='map "$request_method:$oan_legacy_html:$oan_legacy_object_api" $oan_legacy_navigation { default 0; "GET:1:0" 1; "HEAD:1:0" 1; }\n'
    text+='server {\n    listen 80;\n    server_name '+' '.join(sorted(host_map))+';\n    return 308 https://$host$request_uri;\n}\n'
    covered=set()
    for cert in certificates:
        hosts=sorted(set(cert['hosts'])&set(host_map))
        if not hosts:continue
        assert not (set(hosts)&covered),'Overlapping legacy certificate/server names'
        covered.update(hosts)
        text+='server {\n    listen 443 ssl;\n    server_name '+' '.join(hosts)+';\n'
        text+='    ssl_certificate '+cert['fullchain']+';\n    ssl_certificate_key '+cert['privateKey']+';\n'
        text+='    client_max_body_size 100m;\n    proxy_connect_timeout 60s;\n    proxy_send_timeout 300s;\n    proxy_read_timeout 300s;\n'
        text+='    proxy_buffering on;\n    proxy_buffers 8 16k;\n    proxy_buffer_size 16k;\n    proxy_busy_buffers_size 32k;\n'
        text+='    if ($oan_legacy_navigation) { return 307 https://$oan_legacy_canonical$request_uri; }\n'
        text+='    location / {\n        proxy_pass http://istio_ingress;\n        proxy_http_version 1.1;\n'
        text+='        proxy_set_header Host $host;\n        proxy_set_header X-Forwarded-Host $host;\n        proxy_set_header X-Forwarded-Proto https;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n'
        text+='        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection $oan_connection_upgrade;\n    }\n}\n'
    assert covered==set(host_map),'Certificate does not cover every legacy hostname'
    return text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();inventory=json.loads(args.inventory.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True,exist_ok=True)
    host_map={h:canonical(h) for h in inventory['legacyHosts']}
    (args.output/'gateway-and-routes.yaml').write_text(yaml.safe_dump_all(build_routes(host_map,inventory['virtualServices']),sort_keys=False),encoding='utf-8')
    (args.output/'nginx.conf').write_text(build_nginx(host_map,inventory['certificates']),encoding='utf-8')
    (args.output/'host-map.json').write_text(json.dumps(host_map,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'legacyHosts':len(host_map),'output':str(args.output)}))


if __name__=='__main__':main()
