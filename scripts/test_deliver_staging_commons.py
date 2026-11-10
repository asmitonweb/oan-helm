"""Commons staging delivery: the pinned chart exists and is sealed, and the guard names every saved key that would drop."""
import hashlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import commons_values_guard as guard


class DeliverStagingCommons(unittest.TestCase):
    def test_pinned_chart_is_in_the_repository_and_sealed(self):
        version = (ROOT / 'environments/staging/commons-services.chart').read_text(encoding='utf-8').strip()
        archive = f'openg2p-commons-services-{version}.tgz'
        sums = dict(line.split('  ', 1)[::-1] for line in
                    (ROOT / 'repository/SHA256SUMS').read_text(encoding='utf-8').splitlines() if '  ' in line)
        self.assertIn(archive, sums)
        self.assertEqual(hashlib.sha256((ROOT / 'repository' / archive).read_bytes()).hexdigest(), sums[archive])

    def test_guard_names_saved_keys_no_file_sets(self):
        saved = {'keymanager': {'p12KeystorePass': 'x'}, 'master-data': {'geoSeed': {'load': {'samples': False}}}}
        overlay = {'master-data': {'geoSeed': {'load': {'samples': True}}}}
        self.assertEqual(guard.missing(saved, overlay), ['keymanager.p12KeystorePass'])
        self.assertEqual(guard.missing(saved, {**overlay, 'keymanager': {'p12KeystorePass': 'y'}}), [])
        self.assertEqual(guard.missing(None, overlay), [])

    def test_delivery_never_reuses_saved_values(self):
        script = (ROOT / 'scripts/ci/deliver_staging_commons.sh').read_text(encoding='utf-8')
        self.assertIn('--reset-values', script)
        self.assertIn('--atomic', script)
        self.assertNotIn('--reuse-values', script)
        self.assertIn('commons_values_guard.py', script)
        # The guard and the record need only helm, kubectl and the standard library on the deploy agent.
        self.assertNotIn('import yaml', (ROOT / 'scripts/ci/commons_values_guard.py').read_text(encoding='utf-8'))
        # Delivery is decided from the cluster's record, not the changeset, and recorded only after the upgrade.
        self.assertIn('commons-services-delivery', script)
        self.assertLess(script.index('--atomic --wait'), script.index('kubectl create configmap'))
        pipeline = (ROOT / 'ci/jenkins/staging-commons.Jenkinsfile').read_text(encoding='utf-8')
        self.assertNotIn('changeset', pipeline.split('pipeline {', 1)[1])


    def test_base_pin_names_a_version_and_its_archive_hash(self):
        version, sha = (ROOT / 'environments/staging/commons-base.chart').read_text(encoding='utf-8').split()
        self.assertRegex(version, r'^\d+\.\d+\.\d+')
        self.assertRegex(sha, r'^[0-9a-f]{64}$')

    def test_base_delivery_keeps_saved_values_and_never_changes_the_chart_version(self):
        script = (ROOT / 'scripts/ci/deliver_staging_commons_base.sh').read_text(encoding='utf-8')
        # The base release's saved values hold its passwords and cannot be rebuilt from git.
        (flags,) = [line for line in script.splitlines() if line.startswith('flags=')]
        self.assertIn('--reuse-values', flags)
        self.assertNotIn('--reset-values', flags)
        self.assertIn('--atomic', script)
        self.assertIn('sha256sum -c', script)
        self.assertIn('commons-base-delivery', script)
        # A chart version change is refused before anything is downloaded or upgraded.
        self.assertLess(script.index('--reuse-values cannot change the chart'), script.index('helm upgrade "$release"'))
        self.assertLess(script.index('--atomic --wait'), script.index('kubectl create configmap'))
        pipeline = (ROOT / 'ci/jenkins/staging-commons.Jenkinsfile').read_text(encoding='utf-8')
        self.assertLess(pipeline.index('deliver_staging_commons_base.sh'), pipeline.index('deliver_staging_commons.sh "'))

    def test_commons_deliveries_use_their_own_deployer_in_commons_only(self):
        pipeline = (ROOT / 'ci/jenkins/staging-commons.Jenkinsfile').read_text(encoding='utf-8')
        self.assertNotIn('staging-rke2-kubeconfig', pipeline.split('pipeline {', 1)[1])
        self.assertEqual(pipeline.count("credentialsId: 'staging-commons-deployer-kubeconfig'"), 2)
        rbac = (ROOT / 'environments/staging/rbac/commons-deployer-rbac.yaml').read_text(encoding='utf-8')
        body = '\n'.join(line for line in rbac.splitlines() if not line.startswith('#'))
        self.assertNotIn('ClusterRole', body)
        self.assertEqual(set(re.findall(r'namespace: (\S+)', body)), {'commons'})
        self.assertNotIn('"*"', body)


if __name__ == '__main__':
    unittest.main()
