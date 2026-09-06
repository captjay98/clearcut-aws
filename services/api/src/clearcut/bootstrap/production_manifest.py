from typing import Any


class DisallowedProviderError(Exception):
    pass


class ContestProfileValidator:
    APPROVED_MODELS = {"GeminiAdkRuntime"}
    APPROVED_SEARCH = {"ParallelSearchAdapter"}
    APPROVED_EXTRACT = {"ParallelExtractAdapter"}
    APPROVED_MONITOR = {"ParallelMonitorAdapter", "not-enabled"}

    def validate_production_profile(self, config: dict[str, Any]) -> bool:
        runtime = config.get("model_runtime")
        if runtime not in self.APPROVED_MODELS:
            raise DisallowedProviderError(
                f"Unapproved model runtime '{runtime}'. Expected one of {self.APPROVED_MODELS}."
            )

        search = config.get("search_adapter")
        if search not in self.APPROVED_SEARCH:
            raise DisallowedProviderError(
                f"Unapproved search adapter '{search}'. Expected one of {self.APPROVED_SEARCH}."
            )

        extract = config.get("extract_adapter")
        if extract not in self.APPROVED_EXTRACT:
            raise DisallowedProviderError(
                f"Unapproved extract adapter '{extract}'. Expected one of {self.APPROVED_EXTRACT}."
            )

        monitor = config.get("monitor_adapter")
        if monitor not in self.APPROVED_MONITOR:
            raise DisallowedProviderError(
                f"Unapproved monitor adapter '{monitor}'. Expected one of {self.APPROVED_MONITOR}."
            )

        if monitor == "ParallelMonitorAdapter":
            decision = config.get("monitor_decision")
            webhook_proof = config.get("monitor_webhook_proof")
            has_deployed_proof = (
                isinstance(webhook_proof, str)
                and bool(webhook_proof.strip())
                and webhook_proof != "not-available"
            )
            if decision != "GO" or not has_deployed_proof:
                raise DisallowedProviderError(
                    "Monitor requires a recorded GO decision and deployed signed-webhook proof."
                )

        return True
