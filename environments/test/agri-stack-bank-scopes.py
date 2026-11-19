#!/usr/bin/env python3
"""Give the Agri Stack test partner a scope policy at each registry, for OAN's passthrough consent.

OpenG2P's topology runs the Composite in exchange consent mode: the Exchange's Consent Manager issues a
per-registry token on the Composite's behalf, so a registry only checks the Composite's scope policy (step 2 of
OpenG2P's scripts/test_install.py). OAN runs one shared Commons, so the Composite runs in passthrough mode: each
registry receives the partner's own consent, and its Consent Manager asks Partner Management for the *partner's*
policy on that registry's data controller ("unknown_partner ... no active policy for data_controller"). This raises
and approves that policy for the test partner, per registry, with partner-signed consents allowed, reusing the
OpenG2P script's own Partner Management steps. Run it after test_install.py has onboarded the partner (step 4),
then run test_install.py again.

  sudo -E /opt/agri-stack-test/bin/python agri-stack-bank-scopes.py \\
    --agri-stack /opt/src/agri-stack --config agri-stack-test.yaml
"""

import argparse
import sys

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--agri-stack", required=True, help="a checkout of OpenG2P/agri-stack")
p.add_argument("--config", required=True, help="the test_install.py configuration")
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()

sys.path.insert(0, f"{a.agri_stack}/scripts")
import test_install as t  # noqa: E402

run = t.Run(t.Config(a.config), argparse.Namespace(dry_run=a.dry_run, new_key=False, out_dir=t.OUT_DIR, print=False))
try:
    run.check_install()  # reads the use case: its scopes per registry and its purpose
    for controller in sorted(run.scopes):
        needed = [t.policy_input(data_controller=controller, scopes=run.scopes[controller], purposes=[run.purpose],
                                 subject_id_types=run.c.subject_id_types, allow_partner_consents=True)]
        run.ensure_policies(run.c.registries[controller], run.ref, needed, f"partner scope policy {controller}")
except t.InstallTestError as e:
    print("\nERROR: " + str(e), file=sys.stderr)
    sys.exit(e.code)
finally:
    run.close()
