"""New Dev tile correction against immutable chart bytes and the renderer CLI."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

import validate


CHART = validate.ROOT / "charts/openg2p-commons-services"
# Pin the regression to the installed published package, not a future source version.
ARCHIVE = validate.ROOT / "repository/openg2p-commons-services-1.0.0-dev.6.tgz"
DEV_VALUES = validate.ROOT / "environments/dev/values/commons-services.yaml"
RENDERER = Path(__file__).with_name("dev-domain-post-renderer.py")
UI_HOST = "master-data-ui.development.oanstaging.com"
API_HOST = "master-data.development.oanstaging.com"
API_URL = "http://commons-services-master-data-api.commons.svc.cluster.local"
TILE_ENV = "IAM_STAFF_DATA_APPLICATION_URLS__MASTER_DATA_APPLICATION_URL"
JOB = "commons-services-master-data-iam-register-1"
IAM = "commons-services-iam-staff-portal-api"

spec = importlib.util.spec_from_file_location("master_data_renderer", RENDERER)
assert spec is not None and spec.loader is not None
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def resource(docs, kind, name):
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def containers(doc):
    return doc["spec"]["template"]["spec"]["containers"]


def env_item(doc, name):
    return next(e for c in containers(doc) for e in c.get("env", []) if e["name"] == name)


def render(chart, *args):
    return validate.documents(
        validate.run("template", "commons-services", chart, "--namespace", "commons", *args),
        "commons",
    )[0]


class MasterDataTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.published = render(ARCHIVE)
        cls.overlaid = render(ARCHIVE, "-f", DEV_VALUES)

    def run_renderer(self, docs, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(RENDERER), *args],
            input=yaml.safe_dump_all(docs), capture_output=True, text=True,
            encoding="utf-8", check=True,
        )
        self.assertEqual(result.stderr, "")
        return list(yaml.safe_load_all(result.stdout))

    def assert_corrected(self, before, after):
        expected = copy.deepcopy(before)
        env_item(resource(expected, "Job", JOB), "APP_URL")["value"] = "https://" + UI_HOST
        env_item(resource(expected, "Deployment", IAM), TILE_ENV)["value"] = "https://" + UI_HOST
        # All other fields, including ownership, hook annotations and API routes, survive.
        self.assertEqual(after, expected)
        iam_ui = validate.deployment_env(after, "commons-services-iam-staff-ui")
        self.assertEqual(iam_ui["MASTERDATA_API_URL"], API_URL)
        for service, host in [("master-data-api", API_HOST), ("master-data-ui", UI_HOST)]:
            route = resource(after, "VirtualService", "commons-services-" + service)
            self.assertEqual(route["spec"]["hosts"], [host])
            self.assertEqual(
                route["spec"]["http"][0]["route"][0]["destination"],
                {"host": "commons-services-" + service, "port": {"number": 80}},
            )

    def test_dev_overlay_tile_source(self):
        values = validate.read(DEV_VALUES)
        self.assertEqual(
            values["openg2p-iam-service"]["global"]["masterDataApplicationUrl"],
            "https://" + UI_HOST,
        )

    def test_api_url_sources_are_preserved(self):
        for path in [CHART / "values.yaml", DEV_VALUES]:
            with self.subTest(values=str(path.relative_to(validate.ROOT))):
                values = validate.read(path)
                self.assertEqual(values["global"]["masterDataApiUrl"], API_URL)
                for globals_ in [values["global"], values["master-data"]["global"]]:
                    self.assertEqual(globals_["masterDataHostname"], API_HOST)
                    self.assertEqual(globals_["masterDataUiHostname"], UI_HOST)

    def test_published_archive_with_dev_overlay_and_renderer(self):
        self.assert_corrected(self.overlaid, self.run_renderer(self.overlaid))

    def test_published_defaults_with_renderer(self):
        self.assert_corrected(self.published, self.run_renderer(self.published))

    def test_source_with_dev_overlay_and_renderer(self):
        docs = render(CHART, "-f", DEV_VALUES)
        self.assert_corrected(docs, self.run_renderer(docs))

    def test_native_helm_post_renderer_does_not_correct_historical_hook(self):
        # Helm passes ordinary resources, not hook Jobs, to its post-renderer.
        # Keep this limitation visible: the full-manifest CLI checks above do
        # not establish that a normal upgrade repairs the immutable dependency.
        docs = render(ARCHIVE, "-f", DEV_VALUES,
                      "--post-renderer", sys.executable,
                      "--post-renderer-args", str(RENDERER))
        self.assertEqual(env_item(resource(docs, "Deployment", IAM), TILE_ENV)["value"],
                         "https://" + UI_HOST)
        self.assertEqual(env_item(resource(docs, "Job", JOB), "APP_URL")["value"],
                         "https://" + API_HOST)

    def test_idempotent_and_does_not_mutate_input(self):
        original = copy.deepcopy(self.published)
        once = renderer.transform(self.published)
        self.assert_corrected(self.published, once)
        self.assertEqual(renderer.transform(once), once)
        self.assertEqual(self.published, original)

    def test_legacy_canonicalization_and_tile_fix_are_idempotent_together(self):
        for kind, name, key in [("Job", JOB, "APP_URL"), ("Deployment", IAM, TILE_ENV)]:
            with self.subTest(kind=kind):
                doc = copy.deepcopy(resource(self.published, kind, name))
                env_item(doc, key)["value"] = "https://master-data-development.oanstaging.com"
                expected = copy.deepcopy(doc)
                env_item(expected, key)["value"] = "https://" + UI_HOST
                once = renderer.transform(doc)
                self.assertEqual(once, expected)
                self.assertEqual(renderer.transform(once), once)

    def test_preserves_custom_and_staging_urls(self):
        for kind, name, key in [("Job", JOB, "APP_URL"), ("Deployment", IAM, TILE_ENV)]:
            for url in ["https://master-data.staging.oanstaging.com",
                        "https://custom.example.invalid/master-data", "https://" + UI_HOST,
                        "http://" + API_HOST,
                        "https://" + API_HOST + "/", "https://" + API_HOST + "/custom"]:
                with self.subTest(kind=kind, url=url):
                    doc = copy.deepcopy(resource(self.published, kind, name))
                    env_item(doc, key)["value"] = url
                    self.assertEqual(renderer.transform(doc), doc)

    def test_preserves_unrelated_resource_identities(self):
        for kind, name in [("Job", JOB), ("Deployment", IAM)]:
            for change in ["kind", "name", "namespace", "instance", "managed-by", "app-name", "container"]:
                with self.subTest(kind=kind, change=change):
                    doc = copy.deepcopy(resource(self.published, kind, name))
                    if change == "kind":
                        doc["kind"] = "StatefulSet"
                    elif change == "name":
                        doc["metadata"]["name"] = "unrelated-" + name
                    elif change == "namespace":
                        doc["metadata"]["namespace"] = "staging"
                    elif change == "container":
                        containers(doc)[0]["name"] = "unrelated"
                    else:
                        label = "name" if change == "app-name" else change
                        doc["metadata"]["labels"]["app.kubernetes.io/" + label] = "unrelated"
                    self.assertEqual(renderer.transform(doc), doc)

    def test_preserves_other_or_missing_application_mnemonic(self):
        for mnemonic in ["other-app", None]:
            with self.subTest(mnemonic=mnemonic):
                doc = copy.deepcopy(resource(self.published, "Job", JOB))
                entry = env_item(doc, "APP_MNEMONIC")
                if mnemonic is None:
                    containers(doc)[0]["env"].remove(entry)
                else:
                    entry["value"] = mnemonic
                self.assertEqual(renderer.transform(doc), doc)

    def test_only_target_envs_change_in_matching_resources(self):
        for kind, name, target in [("Job", JOB, "APP_URL"), ("Deployment", IAM, TILE_ENV)]:
            with self.subTest(kind=kind):
                doc = copy.deepcopy(resource(self.published, kind, name))
                pod_containers = containers(doc)
                pod_containers[0]["env"].append({"name": "MASTERDATA_API_URL", "value": "https://" + API_HOST})
                unrelated = {"name": "APP_URL" if kind == "Deployment" else TILE_ENV,
                             "value": "https://" + API_HOST}
                pod_containers[0]["env"].append(unrelated)
                pod_containers.append({"name": "unrelated", "env": [
                    {"name": "APP_MNEMONIC", "value": "master-data"},
                    {"name": target, "value": "https://" + API_HOST},
                ]})
                expected = copy.deepcopy(doc)
                env_item(expected, target)["value"] = "https://" + UI_HOST
                self.assertEqual(renderer.transform(doc), expected)

    def test_registration_revision_and_explicit_commons_namespace(self):
        doc = copy.deepcopy(resource(self.published, "Job", JOB))
        doc["metadata"].update(name="commons-services-master-data-iam-register-27", namespace="commons")
        expected = copy.deepcopy(doc)
        env_item(expected, "APP_URL")["value"] = "https://" + UI_HOST
        self.assertEqual(renderer.transform(doc), expected)

    def test_cli_job_skip_contract(self):
        expected = [doc for doc in self.run_renderer(self.overlaid) if doc["kind"] != "Job"]
        self.assertEqual(self.run_renderer(self.overlaid, "--skip-initialization-jobs"), expected)


if __name__ == "__main__":
    unittest.main()
