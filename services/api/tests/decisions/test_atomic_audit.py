"""The legacy ungoverned referral path must not exist on the decision service.

Referrals are governed exclusively through the collaboration slice
(``referral.submit`` / ``referral.acknowledge`` via
:class:`~clearcut.collaboration.application.referrals.ReferralService`), which
carries capability, tenant-and-project scope, expected-version concurrency, an
accountable idempotency receipt, the authoritative audit event, and a
schema-versioned outbox event in one transaction.

The in-memory :class:`DecisionCommandService` previously exposed a parallel,
ungoverned ``refer_clearance_item`` that emitted a competing ``item_referred``
audit action with none of those guarantees. That path is retired; this test pins
its absence so it cannot silently return.
"""

from clearcut.decisions.application.commands import DecisionCommandService


def test_decision_service_has_no_ungoverned_referral_path():
    service = DecisionCommandService()
    # The ungoverned referral method must not exist.
    assert not hasattr(service, "refer_clearance_item")
    # No in-memory referral store remains to support it.
    assert not hasattr(service, "referrals")
