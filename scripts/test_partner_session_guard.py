import copy
from pathlib import Path
import subprocess
import sys
import unittest
import yaml
from partner_session_guard import configure,ISSUER


class PartnerSessionGuardTests(unittest.TestCase):
    def fixture(self):
        return {'apiVersion':'apps/v1','kind':'Deployment','metadata':{
            'name':'commons-services-pm-staff-portal-ui','namespace':'commons',
            'labels':{'app.kubernetes.io/instance':'commons-services'}},'spec':{
            'replicas':1,'template':{'metadata':{'labels':{'keep':'value'}},'spec':{
                'containers':[{'name':'pm-ui','image':'openg2p/partner-management-staff-portal-ui:1.0.2',
                    'env':[{'name':'KEYCLOAK_LOGOUT_URL','value':ISSUER+'/protocol/openid-connect/logout'},
                        {'name':'SECRET_SETTING','valueFrom':{'secretKeyRef':{'name':'keep','key':'key'}}},
                        {'name':'NODE_OPTIONS','value':'--max-old-space-size=512'}]}]}}}}

    def test_preserves_image_secret_wiring_and_ownership(self):
        before=self.fixture();original=copy.deepcopy(before)
        deployment,cm=configure(before)
        self.assertEqual(before,original)
        self.assertEqual(deployment['metadata'],before['metadata'])
        self.assertEqual(deployment['spec']['replicas'],before['spec']['replicas'])
        container=deployment['spec']['template']['spec']['containers'][0]
        self.assertEqual(container['image'],original['spec']['template']['spec']['containers'][0]['image'])
        self.assertIn(original['spec']['template']['spec']['containers'][0]['env'][1],container['env'])
        options=next(e['value'] for e in container['env'] if e['name']=='NODE_OPTIONS')
        self.assertIn('--max-old-space-size=512',options)
        self.assertEqual(cm['metadata']['annotations']['meta.helm.sh/release-name'],'commons-services')
        self.assertEqual(cm['metadata']['name'],'commons-services-pm-session-cookie-guard')

    def test_idempotent(self):
        first,cm=configure(self.fixture());second,cm2=configure(first)
        self.assertEqual(first,second);self.assertEqual(cm,cm2)

    def test_other_environment_rejected(self):
        deployment=self.fixture()
        deployment['spec']['template']['spec']['containers'][0]['env'][0]['value']='https://keycloak.oanstaging.com/realms/staff/protocol/openid-connect/logout'
        with self.assertRaises(AssertionError):configure(deployment)

    def test_full_post_renderer_is_idempotent_and_retains_other_resources(self):
        unrelated={'apiVersion':'v1','kind':'Service','metadata':{'name':'keep'},'spec':{'ports':[{'port':80}]}}
        original=yaml.safe_dump_all([self.fixture(),unrelated])
        command=[sys.executable,str(Path(__file__).with_name('dev-domain-post-renderer.py'))]
        first=subprocess.run(command,input=original,text=True,capture_output=True,check=True).stdout
        second=subprocess.run(command,input=first,text=True,capture_output=True,check=True).stdout
        self.assertEqual(first,second)
        documents=list(yaml.safe_load_all(first))
        self.assertEqual(len(documents),3)
        self.assertIn(unrelated,documents)
        maps=[d for d in documents if d['kind']=='ConfigMap']
        self.assertEqual(len(maps),1)
        self.assertIn('function filterAuthCookies',maps[0]['data']['session-cookie-guard.cjs'])


if __name__=='__main__':unittest.main()
