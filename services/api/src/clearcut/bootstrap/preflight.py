"""Side-effect-free release preflight for hosted deployment profiles."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from clearcut.bootstrap.container import RedactedDeploymentSummary, build_application
from clearcut.bootstrap.settings import ClearcutSettings, DeploymentProfile


def validate_release_profile(
    settings: ClearcutSettings,
    *,
    expected_profile: DeploymentProfile,
) -> RedactedDeploymentSummary:
    """Validate the exact hosted profile without constructing provider clients."""
    if settings.profile is not expected_profile:
        raise RuntimeError(
            f"Expected {expected_profile.value!r} deployment profile, "
            f"received {settings.profile.value!r}."
        )
    if expected_profile in {DeploymentProfile.GCP, DeploymentProfile.AWS}:
        static_delivery = settings.static_delivery
        if (
            not static_delivery.enabled
            or static_delivery.site_dist is None
            or static_delivery.workspace_dist is None
        ):
            raise RuntimeError(
                f"{expected_profile.value.upper()} release requires enabled site and workspace static delivery paths."
            )
    return build_application(settings).summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a ClearCut release profile")
    parser.add_argument(
        "--expected-profile",
        choices=(DeploymentProfile.GCP.value, DeploymentProfile.AWS.value),
        required=True,
    )

    args = parser.parse_args()
    expected_profile = DeploymentProfile(args.expected_profile)
    summary = validate_release_profile(
        ClearcutSettings.from_environment(),
        expected_profile=expected_profile,
    )
    print(json.dumps(asdict(summary), sort_keys=True))


if __name__ == "__main__":
    main()
