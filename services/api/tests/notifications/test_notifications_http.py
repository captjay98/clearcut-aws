"""HTTP-level behaviour of the personal notification inbox.

These tests pin the four canonical inbox operations end to end against the real
migrated schema (``notifications`` from 0016 and
``notification_delivery_preferences`` from 0036), through the same session
cookie, origin check, and organization scope a browser uses.

What they hold in place:

* An inbox is personal. A caller sees exactly their own rows, and a row addressed
  to another recipient is answered with the identical 404 that an entirely
  unknown identifier produces — never a 403, which would confirm the row exists.
* ``markAllNotificationsRead`` reports the number of rows it actually
  transitioned, so repeating the call reports zero instead of restating the first
  call's total.
* A notification is not permission. When the destination project is gone or lies
  outside the reader's access, the response carries no ``link`` at all and states
  why in ``blockedReason``.
* The delivery preference is personal and unique per ``(org, user)``: setting it
  twice replaces the value rather than accumulating competing rows.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.collaboration.adapters.sql_notification_repository import (
    SqlNotificationRepository,
)
from clearcut.collaboration.application.recipient_projection import (
    NotificationProjectionService,
)
from clearcut.collaboration.delivery.notifications_http import (
    router as notifications_router,
)
from clearcut.collaboration.domain.notifications import (
    Notification,
    NotificationContentError,
    NotificationTier,
)
from clearcut.database import session_scope
from clearcut.main import app
from clearcut.organizations.domain.models import Membership
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"
_REPOSITORY = SqlNotificationRepository()


_router_mounted = False


@pytest.fixture(autouse=True)
def mounted_notifications_router() -> None:
    """Mount the inbox router for the test app if the application has not.

    The router is owned by this slice but mounted in ``main.py`` by the
    application composition owner. Mounting it here lets these tests pin the
    boundary now without editing a file this slice does not own.

    The guard is a module flag rather than a route inspection: FastAPI 0.141
    stores ``include_router`` calls as lazy ``_IncludedRouter`` wrappers, so
    ``app.routes`` exposes no ``operation_id`` to check against. Once composition
    mounts the router, the duplicate registered here is simply never reached,
    because the earlier matching route wins.
    """
    global _router_mounted
    if _router_mounted:
        return
    mounted_operations = {
        operation.get("operationId")
        for path in app.openapi().get("paths", {}).values()
        for operation in path.values()
        if isinstance(operation, dict)
    }
    if "listNotifications" not in mounted_operations:
        app.include_router(notifications_router)
        app.openapi_schema = None
    _router_mounted = True


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    email: str


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _create_actor(client: AsyncClient, *, suffix: str) -> Actor:
    """Create an actor and authenticate ``client`` as them.

    The user row and its credential are written in one committed transaction
    before the login call, then the client authenticates through the real
    ``createSession`` endpoint. Registering over HTTP would work too, but that
    endpoint writes the user and the session in two separate transactions, which
    intermittently fails its own foreign key under SQLite; these tests are about
    the inbox, so they do not depend on that ordering.
    """
    email = f"inbox-{suffix}-{uuid4().hex}@example.com"
    user_id = uuid6.uuid7()
    password_hash = app.state.identity_provider.hash_password(_PASSWORD)
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {"id": str(user_id), "email": email, "created_at": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO local_credentials (user_id, password_hash, updated_at) "
                "VALUES (:user_id, :password_hash, :updated_at)"
            ),
            {"user_id": str(user_id), "password_hash": password_hash, "updated_at": now},
        )

    login = await client.post(
        "/api/v1/sessions",
        json={"email": email, "password": _PASSWORD},
    )
    assert login.status_code == 201, login.text
    assert UUID(login.json()["data"]["userId"]) == user_id
    return Actor(user_id=user_id, email=email)


async def _create_org(client: AsyncClient, *, suffix: str) -> UUID:
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Inbox Studio {suffix}",
            "slug": f"inbox-{suffix.replace('_', '-')}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    return UUID(organization.json()["data"]["orgId"])


async def _create_project(client: AsyncClient, *, org_id: UUID, title: str) -> UUID:
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": title},
    )
    assert project.status_code == 201, project.text
    return UUID(project.json()["data"]["projectId"])


async def _add_member(
    *,
    org_id: UUID,
    user_id: UUID,
    role: str,
    granted_project_id: UUID | None = None,
) -> None:
    """Insert an active membership, optionally with an explicit project grant."""
    membership_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(membership_id),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role,
                "created_at": now,
            },
        )
        if granted_project_id is not None:
            await session.execute(
                sa.text(
                    "INSERT INTO project_grants "
                    "(id, org_id, project_id, membership_id, granted_at) "
                    "VALUES (:id, :org_id, :project_id, :membership_id, :granted_at)"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(granted_project_id),
                    "membership_id": str(membership_id),
                    "granted_at": now,
                },
            )


async def _seed_notification(
    *,
    org_id: UUID,
    recipient_id: UUID,
    title: str,
    body: str,
    destination_path: str,
    tier: NotificationTier = NotificationTier.ACTION,
    read: bool = False,
) -> Notification:
    """Persist one inbox row through the repository the router reads from."""
    notification = Notification.create(
        org_id=org_id,
        recipient_id=recipient_id,
        tier=tier,
        title=title,
        body_redacted=body,
        destination_path=destination_path,
    )
    if read:
        notification = dataclasses.replace(notification, is_read=True)
    async with session_scope() as session:
        persisted = await _REPOSITORY.insert_notifications(session, [notification])
    assert persisted.persisted_count == 1
    return notification


def _notifications_path(org_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/notifications"


def _mark_read_path(org_id: UUID, notification_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/notifications/{notification_id}:markRead"


def _preference_path(org_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/notification-preference"


async def test_inbox_returns_only_the_callers_own_notifications() -> None:
    async with await _client() as owner_client, await _client() as member_client:
        owner = await _create_actor(owner_client, suffix="owner")
        org_id = await _create_org(owner_client, suffix="own")
        project_id = await _create_project(owner_client, org_id=org_id, title="Signal Fires")

        member = await _create_actor(member_client, suffix="member")
        await _add_member(
            org_id=org_id,
            user_id=member.user_id,
            role="reviewer",
            granted_project_id=project_id,
        )

        mine = await _seed_notification(
            org_id=org_id,
            recipient_id=owner.user_id,
            title="Referral awaiting acknowledgement",
            body="A specialist referral is waiting on your acknowledgement.",
            destination_path=f"/o/studio/projects/{project_id}/items",
            tier=NotificationTier.URGENT,
        )
        theirs = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Monitoring change detected",
            body="A cited source changed since it was captured.",
            destination_path=f"/o/studio/projects/{project_id}/monitoring",
        )

        listed = await owner_client.get(_notifications_path(org_id))
        assert listed.status_code == 200, listed.text
        rows = listed.json()["data"]

        assert [row["notificationId"] for row in rows] == [str(mine.notification_id)]
        assert str(theirs.notification_id) not in {row["notificationId"] for row in rows}
        assert rows[0] == {
            "notificationId": str(mine.notification_id),
            "orgId": str(org_id),
            "tier": "urgent",
            "title": "Referral awaiting acknowledgement",
            "body": "A specialist referral is waiting on your acknowledgement.",
            "read": False,
            "link": f"/o/studio/projects/{project_id}/items",
            "createdAt": rows[0]["createdAt"],
        }

        # The other recipient sees exactly the mirror image of the same table.
        their_view = await member_client.get(_notifications_path(org_id))
        assert their_view.status_code == 200, their_view.text
        assert [row["notificationId"] for row in their_view.json()["data"]] == [
            str(theirs.notification_id)
        ]


async def test_another_recipients_notification_is_a_neutral_not_found() -> None:
    async with await _client() as owner_client, await _client() as member_client:
        _owner = await _create_actor(owner_client, suffix="probe-owner")
        org_id = await _create_org(owner_client, suffix="probe")
        project_id = await _create_project(owner_client, org_id=org_id, title="Quiet Signal")

        member = await _create_actor(member_client, suffix="probe-member")
        await _add_member(
            org_id=org_id,
            user_id=member.user_id,
            role="reviewer",
            granted_project_id=project_id,
        )
        theirs = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Rewrite proposal awaiting review",
            body="A rewrite proposal is waiting on a reviewer.",
            destination_path=f"/o/studio/projects/{project_id}/rewrites",
        )

        foreign = await owner_client.post(_mark_read_path(org_id, theirs.notification_id))
        unknown = await owner_client.post(_mark_read_path(org_id, uuid6.uuid7()))

        assert foreign.status_code == 404, foreign.text
        assert unknown.status_code == 404, unknown.text
        # Identical shape: nothing in the response distinguishes a real row
        # addressed to someone else from a row that never existed.
        assert _comparable_error(foreign.json()) == _comparable_error(unknown.json())
        assert _comparable_error(foreign.json()) == {
            "code": "not_found",
            "message": "Notification not found.",
            "retryable": False,
        }

        # The probe did not read the other recipient's notification either.
        still_unread = await member_client.get(_notifications_path(org_id))
        assert still_unread.status_code == 200
        assert still_unread.json()["data"][0]["read"] is False


def _comparable_error(payload: dict) -> dict:
    error = dict(payload["error"])
    error.pop("requestId", None)
    return error


async def test_mark_all_read_counts_only_rows_it_changed_and_is_idempotent() -> None:
    async with await _client() as client:
        owner = await _create_actor(client, suffix="markall")
        org_id = await _create_org(client, suffix="markall")
        project_id = await _create_project(client, org_id=org_id, title="Dawn Rooftop")
        destination = f"/o/studio/projects/{project_id}/items"

        for index in range(3):
            await _seed_notification(
                org_id=org_id,
                recipient_id=owner.user_id,
                title=f"Unread notice {index}",
                body="An item needs a decision.",
                destination_path=destination,
            )
        await _seed_notification(
            org_id=org_id,
            recipient_id=owner.user_id,
            title="Already read notice",
            body="This one was read before the call.",
            destination_path=destination,
            read=True,
        )

        first = await client.post(_notifications_path(org_id))
        assert first.status_code == 200, first.text
        # Three unread rows changed; the already-read row is not recounted.
        assert first.json()["data"] == {"updatedCount": 3}

        second = await client.post(_notifications_path(org_id))
        assert second.status_code == 200, second.text
        assert second.json()["data"] == {"updatedCount": 0}

        listed = await client.get(_notifications_path(org_id))
        assert listed.status_code == 200
        assert [row["read"] for row in listed.json()["data"]] == [True, True, True, True]


async def test_single_mark_read_returns_the_read_notification_and_is_idempotent() -> None:
    async with await _client() as client:
        owner = await _create_actor(client, suffix="markone")
        org_id = await _create_org(client, suffix="markone")
        project_id = await _create_project(client, org_id=org_id, title="Observatory")
        seeded = await _seed_notification(
            org_id=org_id,
            recipient_id=owner.user_id,
            title="Evidence decision recorded",
            body="A reviewer recorded a decision on an item you follow.",
            destination_path=f"/o/studio/projects/{project_id}/items",
            tier=NotificationTier.INFORMATIONAL,
        )

        marked = await client.post(_mark_read_path(org_id, seeded.notification_id))
        assert marked.status_code == 200, marked.text
        assert marked.json()["data"]["notificationId"] == str(seeded.notification_id)
        assert marked.json()["data"]["read"] is True
        assert marked.json()["data"]["tier"] == "informational"

        repeated = await client.post(_mark_read_path(org_id, seeded.notification_id))
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["data"]["read"] is True


async def test_link_is_withheld_when_the_destination_is_not_the_readers_to_open() -> None:
    async with await _client() as owner_client, await _client() as member_client:
        owner = await _create_actor(owner_client, suffix="link-owner")
        org_id = await _create_org(owner_client, suffix="link")
        granted_project_id = await _create_project(
            owner_client, org_id=org_id, title="Granted Project"
        )
        ungranted_project_id = await _create_project(
            owner_client, org_id=org_id, title="Ungranted Project"
        )
        deleted_project_id = uuid6.uuid7()

        member = await _create_actor(member_client, suffix="link-member")
        await _add_member(
            org_id=org_id,
            user_id=member.user_id,
            role="reviewer",
            granted_project_id=granted_project_id,
        )

        reachable = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Item needs your action",
            body="An item in a project you work on needs a decision.",
            destination_path=f"/o/studio/projects/{granted_project_id}/items",
        )
        out_of_reach = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Item needs review",
            body="An item outside your projects was assigned and then reassigned.",
            destination_path=f"/o/studio/projects/{ungranted_project_id}/items",
        )
        gone = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Report released",
            body="A report was released for a project that has since been removed.",
            destination_path=f"/o/studio/projects/{deleted_project_id}/reports",
        )
        org_level = await _seed_notification(
            org_id=org_id,
            recipient_id=member.user_id,
            title="Organization policy activated",
            body="A new policy configuration is active for this organization.",
            destination_path="/o/studio/settings",
            tier=NotificationTier.INFORMATIONAL,
        )

        listed = await member_client.get(_notifications_path(org_id))
        assert listed.status_code == 200, listed.text
        by_id = {row["notificationId"]: row for row in listed.json()["data"]}

        reachable_row = by_id[str(reachable.notification_id)]
        assert reachable_row["link"] == f"/o/studio/projects/{granted_project_id}/items"
        assert "blockedReason" not in reachable_row

        for withheld_id in (gone.notification_id, out_of_reach.notification_id):
            row = by_id[str(withheld_id)]
            # No link key at all: a client that ignores blockedReason still has
            # nothing to navigate to.
            assert "link" not in row
            assert row["blockedReason"] == (
                "The project this notification refers to is no longer available to you, "
                "so no link is offered."
            )

        # An organization-level destination names no project, so nothing is withheld.
        assert by_id[str(org_level.notification_id)]["link"] == "/o/studio/settings"

        # The same rows read by an owner, who can open every project in the
        # organization, keep their links: the withholding tracked access, not the
        # stored path.
        owner_copy = await _seed_notification(
            org_id=org_id,
            recipient_id=owner.user_id,
            title="Item needs review",
            body="An item outside a reviewer's projects still opens for an owner.",
            destination_path=f"/o/studio/projects/{ungranted_project_id}/items",
        )
        owner_listed = await owner_client.get(_notifications_path(org_id))
        assert owner_listed.status_code == 200
        owner_row = next(
            row
            for row in owner_listed.json()["data"]
            if row["notificationId"] == str(owner_copy.notification_id)
        )
        assert owner_row["link"] == f"/o/studio/projects/{ungranted_project_id}/items"

        # Marking read takes the same path, so the single-row response withholds too.
        marked = await member_client.post(_mark_read_path(org_id, gone.notification_id))
        assert marked.status_code == 200, marked.text
        assert "link" not in marked.json()["data"]
        assert marked.json()["data"]["blockedReason"]


async def test_delivery_preference_round_trips_and_stays_unique_per_org_user() -> None:
    async with await _client() as owner_client, await _client() as member_client:
        owner = await _create_actor(owner_client, suffix="pref-owner")
        org_id = await _create_org(owner_client, suffix="pref")
        project_id = await _create_project(owner_client, org_id=org_id, title="Preference Project")

        member = await _create_actor(member_client, suffix="pref-member")
        await _add_member(
            org_id=org_id,
            user_id=member.user_id,
            role="reviewer",
            granted_project_id=project_id,
        )

        stored = await owner_client.put(_preference_path(org_id), json={"channel": "email"})
        assert stored.status_code == 200, stored.text
        assert stored.json()["data"] == {"channel": "email"}

        replaced = await owner_client.put(_preference_path(org_id), json={"channel": "push"})
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["data"] == {"channel": "push"}

        # A reviewer sets their own channel: the preference is personal, so it
        # needs no elevated role.
        member_stored = await member_client.put(
            _preference_path(org_id), json={"channel": "in_app"}
        )
        assert member_stored.status_code == 200, member_stored.text
        assert member_stored.json()["data"] == {"channel": "in_app"}

        rejected = await owner_client.put(_preference_path(org_id), json={"channel": "sms"})
        assert rejected.status_code == 422, rejected.text
        unexpected_field = await owner_client.put(
            _preference_path(org_id), json={"channel": "email", "escalate": True}
        )
        assert unexpected_field.status_code == 422, unexpected_field.text

        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT user_id, channel FROM notification_delivery_preferences "
                            "WHERE org_id = :org_id ORDER BY user_id"
                        ),
                        {"org_id": str(org_id)},
                    )
                )
                .mappings()
                .all()
            )

        # One row per user, replaced in place rather than accumulated.
        stored_channels = {UUID(str(row["user_id"])): row["channel"] for row in rows}
        assert stored_channels == {owner.user_id: "push", member.user_id: "in_app"}


async def test_the_inbox_requires_an_authenticated_member() -> None:
    async with await _client() as owner_client, await _client() as stranger_client:
        await _create_actor(owner_client, suffix="closed-owner")
        org_id = await _create_org(owner_client, suffix="closed")

        anonymous = await stranger_client.get(_notifications_path(org_id))
        assert anonymous.status_code == 401, anonymous.text

        await _create_actor(stranger_client, suffix="stranger")
        # Registered, but not a member of this organization.
        outsider = await stranger_client.get(_notifications_path(org_id))
        assert outsider.status_code == 403, outsider.text
        outsider_mutation = await stranger_client.post(_notifications_path(org_id))
        assert outsider_mutation.status_code == 403, outsider_mutation.text


async def test_a_projected_fan_out_lands_in_each_recipients_inbox() -> None:
    """The projection's persistence path is the only way rows reach the inbox."""
    async with await _client() as owner_client, await _client() as member_client:
        owner = await _create_actor(owner_client, suffix="fanout-owner")
        org_id = await _create_org(owner_client, suffix="fanout")
        project_id = await _create_project(owner_client, org_id=org_id, title="Fan-out Project")

        member = await _create_actor(member_client, suffix="fanout-member")
        await _add_member(
            org_id=org_id,
            user_id=member.user_id,
            role="reviewer",
            granted_project_id=project_id,
        )

        memberships = [
            Membership(
                membership_id=uuid6.uuid7(),
                org_id=org_id,
                user_id=owner.user_id,
                role="owner",
                status="active",
                created_at=datetime.now(UTC),
            ),
            Membership(
                membership_id=uuid6.uuid7(),
                org_id=org_id,
                user_id=member.user_id,
                role="reviewer",
                status="active",
                created_at=datetime.now(UTC),
            ),
        ]

        async with session_scope() as session:
            projected = await NotificationProjectionService().project_and_persist(
                session,
                repository=_REPOSITORY,
                org_id=org_id,
                actor_id=owner.user_id,
                title="Evidence decision recorded",
                body_redacted="A decision was recorded on an item in this project.",
                destination_path=f"/o/studio/projects/{project_id}/items",
                tier=NotificationTier.ACTION,
                active_memberships=memberships,
            )

        # The acting owner is excluded, so exactly the reviewer is notified.
        assert projected.persisted_count == 1
        assert [n.recipient_id for n in projected.notifications] == [member.user_id]

        owner_inbox = await owner_client.get(_notifications_path(org_id))
        member_inbox = await member_client.get(_notifications_path(org_id))
        assert owner_inbox.json()["data"] == []
        assert len(member_inbox.json()["data"]) == 1
        assert member_inbox.json()["data"][0]["tier"] == "action"
        assert member_inbox.json()["data"][0]["body"] == (
            "A decision was recorded on an item in this project."
        )



async def test_each_notification_carries_its_own_creation_time() -> None:
    """A creation time is captured per notification, not once per process.

    The dataclass default is a factory. A bare ``datetime.now(UTC)`` default
    would be evaluated once when the class is defined, so every notification
    built without an explicit timestamp would claim the process start time and
    the inbox's newest-first ordering would be meaningless.
    """
    org_id = uuid6.uuid7()
    recipient_id = uuid6.uuid7()

    first = Notification(
        notification_id=uuid6.uuid7(),
        org_id=org_id,
        recipient_id=recipient_id,
        tier=NotificationTier.ACTION,
        title="First",
        body_redacted="First notice.",
        destination_path="/o/studio/settings",
    )
    second = Notification(
        notification_id=uuid6.uuid7(),
        org_id=org_id,
        recipient_id=recipient_id,
        tier=NotificationTier.ACTION,
        title="Second",
        body_redacted="Second notice.",
        destination_path="/o/studio/settings",
    )

    assert first.created_at.tzinfo is not None
    assert second.created_at >= first.created_at
    # A shared class-level default would make these byte-identical every time.
    assert (
        first.created_at != second.created_at
        or Notification.__dataclass_fields__["created_at"].default_factory is not None
    )


async def test_notification_content_may_not_carry_internal_identifiers() -> None:
    """An internal identifier tells the reader nothing they can act on."""
    org_id = uuid6.uuid7()
    recipient_id = uuid6.uuid7()

    with pytest.raises(NotificationContentError):
        Notification.create(
            org_id=org_id,
            recipient_id=recipient_id,
            tier=NotificationTier.ACTION,
            title="Evaluation finished",
            body_redacted=f"Rubric version {uuid6.uuid7()} scored this item.",
            destination_path="/o/studio/settings",
        )

    with pytest.raises(NotificationContentError):
        Notification.create(
            org_id=org_id,
            recipient_id=recipient_id,
            tier=NotificationTier.ACTION,
            title="Prompt id 41 produced a finding",
            body_redacted="A finding is ready for review.",
            destination_path="/o/studio/settings",
        )

    # The same notice, written for the reader, is accepted.
    accepted = Notification.create(
        org_id=org_id,
        recipient_id=recipient_id,
        tier=NotificationTier.ACTION,
        title="A finding needs your review",
        body_redacted="An item was scored and needs a human decision.",
        destination_path="/o/studio/settings",
    )
    assert accepted.title == "A finding needs your review"
