"""Legacy aliases retain routing, while only HTML navigations redirect."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('compatibility',Path(__file__).with_name('prepare-legacy-compatibility.py'))
compatibility=importlib.util.module_from_spec(spec);spec.loader.exec_module(compatibility)


class LegacyCompatibilityTests(unittest.TestCase):
    def test_alias_keeps_route_paths_and_destinations(self):
        hostmap={'staff-farmer-development.oanstaging.com':'staff-farmer.development.oanstaging.com'}
        source={'metadata':{'name':'farmer-staff','namespace':'farmer'},'spec':{'hosts':['staff-farmer.development.oanstaging.com'],'gateways':['istio-system/development'],'http':[{'match':[{'uri':{'prefix':'/auth/'}}],'route':[{'destination':{'host':'api.farmer.svc.cluster.local','port':{'number':80}}}]}]}}
        documents=compatibility.build_routes(hostmap,[source]);legacy=documents[1]
        self.assertEqual(legacy['spec']['http'],source['spec']['http'])
        self.assertEqual(legacy['spec']['gateways'],['istio-system/development-legacy'])
        self.assertEqual(legacy['spec']['hosts'],list(hostmap))
        self.assertNotIn('meta.helm.sh/release-name',legacy['metadata'].get('annotations',{}))

    def test_missing_canonical_route_fails(self):
        with self.assertRaises(AssertionError):compatibility.build_routes({'missing-development.oanstaging.com':'missing.development.oanstaging.com'},[])

    def test_odk_retains_older_enketo_host_with_canonical_route(self):
        hostmap={'odk-central-development.oanstaging.com':'odk-central.development.oanstaging.com'}
        source={'metadata':{'name':'commons-services-odk-central','namespace':'commons'},
            'spec':{'hosts':['odk-central.development.oanstaging.com'],
                'gateways':['istio-system/development'],
                'http':[{'headers':{'request':{'set':{'x-forwarded-host':'odk-central.development.oanstaging.com'}}},
                    'route':[{'destination':{'host':'commons-services-odk-central-frontend','port':{'number':80}}}]}]}}
        documents=compatibility.build_routes(hostmap,[source])
        expected=['odk-central-development.oanstaging.com','odk.commons-dev.oanstaging.com']
        self.assertEqual(documents[0]['spec']['servers'][0]['hosts'],expected)
        self.assertEqual(documents[1]['spec']['hosts'],expected)
        self.assertEqual(documents[1]['spec']['http'],source['spec']['http'])
        self.assertEqual(documents[1]['spec']['gateways'],['istio-system/development-legacy'])
        self.assertEqual(source['spec']['hosts'],['odk-central.development.oanstaging.com'])
        self.assertEqual(len(hostmap),1)

    def test_browser_navigation_is_temporary_and_post_keeps_proxy(self):
        old='staff-farmer-development.oanstaging.com'
        text=compatibility.build_nginx({old:'staff-farmer.development.oanstaging.com'},[{'hosts':[old],'fullchain':'/protected/fullchain.pem','privateKey':'/protected/privkey.pem'}])
        self.assertIn('"GET:1:0" 1; "HEAD:1:0" 1;',text)
        self.assertIn('minio-farmer-development.oanstaging.com 1;',text)
        self.assertNotIn('"GET:1:1" 1;',text)
        self.assertNotIn('"POST:1"',text)
        self.assertIn('return 307 https://$oan_legacy_canonical$request_uri',text)
        self.assertIn('proxy_set_header Host $host;',text)
        self.assertIn('proxy_buffer_size 16k;',text)

    def test_missing_tls_coverage_fails(self):
        with self.assertRaises(AssertionError):compatibility.build_nginx({'old-development.oanstaging.com':'old.development.oanstaging.com'},[])


if __name__=='__main__':unittest.main()
