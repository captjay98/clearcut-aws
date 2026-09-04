"""Shared typed projection for governed decision-slice results.

Both governed decision commands — recording an evidence decision and setting a
workflow disposition — project the same loaded :class:`ScopedItem` onto the same
:class:`PersistedDecision` result, differing only in which two mutable fields
they carry forward:

* an evidence decision advances the clearance ``status`` and leaves the
  disposition untouched;
* a disposition advances the ``disposition_status`` and, because a disposition
  is a workflow signal only, leaves the clearance ``status`` untouched.

Every other field is copied straight from the loaded item. This single helper
holds that copy so the two services cannot drift, while each service stays in
control of the two fields that are actually specific to it by passing them
explicitly. The helper changes no behavior: callers pass exactly the ``status``
and ``disposition_status`` they previously assembled inline.
"""

from __future__ import annotations

from uuid import UUID

from clearcut.decisions.ports.repository import PersistedDecision, ScopedItem


def project_decision(
    item: ScopedItem,
    *,
    decision_id: UUID,
    resulting_version: int,
    status: str,
    disposition_status: str | None,
) -> PersistedDecision:
    """Project a loaded item onto the committed decision result.

    ``status`` and ``disposition_status`` are supplied by the caller: an evidence
    decision passes the deterministic post-decision status and the item's
    unchanged disposition, while a disposition passes the item's unchanged status
    and the new disposition value. Every other field is carried forward from the
    loaded item unchanged.
    """
    return PersistedDecision(
        decision_id=decision_id,
        item_id=item.item_id,
        org_id=item.org_id,
        project_id=item.project_id,
        version_id=item.version_id,
        category=item.category,
        entity_name=item.entity_name,
        status=status,
        disposition_status=disposition_status,
        assigned_to_user_id=item.assigned_to_user_id,
        context_text=item.context_text,
        resulting_version=resulting_version,
        cited_claim_count=item.cited_claim_count,
    )


__all__ = ["project_decision"]
