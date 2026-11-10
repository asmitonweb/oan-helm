"""Isolated template contracts; candidate promotion gates remain unconditional."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml
from validate import fingerprint

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get('HELM', 'helm')


class RefactorContracts(unittest.TestCase):
    def test_chart_seal_rejects_windows_only_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            chart=Path(tmp)
            source=chart/'Chart.yaml'
            source.write_bytes(b'apiVersion: v2\r\nname: verification\r\n')
            with self.assertRaisesRegex(AssertionError,'repository LF line endings'):
                fingerprint(chart)
            source.write_bytes(b'apiVersion: v2\nname: verification\n')
            self.assertEqual(len(fingerprint(chart)),64)

    def test_master_data_images_are_pinned_and_seed_is_off(self):
        values = yaml.safe_load((ROOT/'charts/openg2p-commons-services/values.yaml').read_text(encoding='utf-8'))['master-data']
        for component in ('masterDataAPI','masterDataUi'):
            self.assertEqual(values[component]['image']['tag'],'0.0.0-develop.118')
            self.assertRegex(values[component]['image']['digest'],r'^sha256:[0-9a-f]{64}$')
        self.assertFalse(values['geoSeed']['enabled'])
        self.assertFalse(values['geoSeed']['load']['samples'])
        self.assertFalse(values['geoSeed']['autoPublish'])

    def test_only_staging_loads_the_pack_sample_people(self):
        load = lambda env: yaml.safe_load((ROOT/f'environments/{env}/values/commons-services.yaml').read_text(
            encoding='utf-8'))['master-data']['geoSeed']['load']
        self.assertTrue(load('staging')['samples'])
        self.assertFalse(load('dev')['samples'])
        self.assertFalse(load('dev')['geo'])
        # Staging: true only for the first load of the geography cutover (master_data renamed
        # away first); the follow-up sets it back to false.
        self.assertTrue(load('staging')['geo'])

    def test_seed_image_is_the_recorded_eth_oan_build(self):
        # The newest release-train manifest that records the seed image.
        manifests = sorted(ROOT.glob('releases/1.0.0-dev.*.yaml'),key=lambda p:int(p.stem.rsplit('.',1)[1]),reverse=True)
        recorded = next(c['masterDataSeedImage'] for m in manifests
                        for c in yaml.safe_load(m.read_text(encoding='utf-8'))['charts']
                        if c['name']=='openg2p-commons-services' and 'masterDataSeedImage' in c)
        values = yaml.safe_load((ROOT/'charts/openg2p-commons-services/values.yaml').read_text(encoding='utf-8'))['master-data']
        self.assertEqual(values['geoSeed']['image']['repository'],recorded['repository'])
        self.assertEqual(values['geoSeed']['image']['tag'],recorded['tag']+'@'+recorded['digest'])
        self.assertEqual(values['geoSeed']['countryPack'],recorded['countryPack'])
        # The seed loader must come from the same Master Data build as the API.
        base = recorded['base'].split('@')[0]
        self.assertEqual(base.rsplit(':',1)[1],values['masterDataAPI']['image']['tag'])

    def render(self, chart, *args):
        return subprocess.run([HELM,'template','test',str(chart),*args],capture_output=True,text=True,encoding='utf-8')

    def test_dashboard_auth_digest_and_pull_settings(self):
        for domain in ('cropsown','livestock'):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as tmp:
                source = ROOT/f'charts/openg2p-{domain}-registry'
                fixture = Path(tmp)
                (fixture/'templates').mkdir()
                # Render only the reporting API template, without registry workloads.
                # The real chart gate is neither edited nor bypassed for deployment.
                for name in ('_oan.tpl','_reporting.tpl','dashboard-api.yaml'):
                    shutil.copyfile(source/'templates'/name,fixture/'templates'/name)
                (fixture/'Chart.yaml').write_text('apiVersion: v2\nname: auth-contract\nversion: 1.0.0+test\n')
                values = yaml.safe_load((source/'values.yaml').read_text(encoding='utf-8'))
                values['dashboardApi'].update({'enabled':True,'image':{'repository':'example.invalid/api','digest':'sha256:'+'a'*64},
                    'imagePullSecrets':[{'name':'preserved-pull'}],'envFrom':[{'secretRef':{'name':'preserved-env'}}]})
                values['dashboardApi']['auth']['issuer']='https://iam.verification.invalid/realms/staff'
                (fixture/'values.yaml').write_text(yaml.safe_dump(values))
                result = self.render(fixture)
                self.assertEqual(result.returncode,0,result.stderr)
                deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc['kind']=='Deployment')
                pod = deployment['spec']['template']['spec']
                container = pod['containers'][0]
                env = {item['name']:item for item in container['env']}
                self.assertEqual(env['AUTH_ENABLED']['value'],'true')
                self.assertEqual(env['AUTH_ROLE']['value'],'charts:read')
                self.assertEqual(container['image'],'example.invalid/api@sha256:'+'a'*64)
                self.assertEqual(pod['imagePullSecrets'],[{'name':'preserved-pull'}])
                self.assertEqual(container['envFrom'],[{'secretRef':{'name':'preserved-env'}}])
                self.assertIn('secretKeyRef',env['PGPASSWORD']['valueFrom'])
                for settings, message in [(['--set','dashboardApi.auth.enabled=false'],'require dashboardApi.auth.enabled=true'),
                    (['--set','dashboardApi.auth.issuer=','--set','dashboardApi.auth.iamUrl='],'issuer or dashboardApi.auth.iamUrl is required'),
                    (['--set','dashboardApi.env.AUTH_ENABLED=false'],'reserved authentication settings')]:
                    rejected = self.render(fixture,*settings)
                    self.assertNotEqual(rejected.returncode,0)
                    self.assertIn(message,rejected.stderr)


if __name__=='__main__': unittest.main()
