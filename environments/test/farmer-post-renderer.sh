#!/usr/bin/env bash
# Helm post-renderer for the Farmer registry on registry-test: the farmer-registry repository's own render corrections
# (ci/deploy/oan_compat.py), run directly instead of in its CI Docker image. OAN_PROMOTED_VALUES is the renderer's
# path for a chart that has no dev/staging pin of its own (this test chart is New Dev's build, used on another host).
set -euo pipefail
cd "$FARMER_REGISTRY_SRC/ci/deploy"
DELIVERY_ENVIRONMENT=dev OAN_PROMOTED_VALUES="$OAN_TEST_VALUES" OAN_CHART_ONLY=false exec python3 oan_compat.py
