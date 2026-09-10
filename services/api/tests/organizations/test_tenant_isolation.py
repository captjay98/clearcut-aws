import pytest
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_tenant_isolation_and_cross_organization_denial():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User A
        res_a = await client.post(
            "/api/v1/users",
            json={"name": "Alice User", "email": "alice@studio-a.com", "password": "Password123!"},
        )
        assert res_a.status_code == 201
        cookie_a = res_a.cookies.get("clearcut_session")
        assert cookie_a is not None

        # Register User B
        res_b = await client.post(
            "/api/v1/users",
            json={"name": "Bob User", "email": "bob@studio-b.com", "password": "Password123!"},
        )
        assert res_b.status_code == 201
        cookie_b = res_b.cookies.get("clearcut_session")
        assert cookie_b is not None

        # User A creates Org A
        client.cookies.set("clearcut_session", cookie_a)
        org_a_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Studio Alpha", "slug": "studio-alpha"},
        )
        assert org_a_res.status_code == 201
        org_a_id = org_a_res.json()["data"]["orgId"]

        # User A creates a project in Org A
        proj_res = await client.post(
            f"/api/v1/organizations/{org_a_id}/projects",
            json={"title": "Alpha Secret Project", "description": "Top secret"},
        )
        assert proj_res.status_code == 201
        proj_id = proj_res.json()["data"]["projectId"]

        # User B creates Org B
        client.cookies.set("clearcut_session", cookie_b)
        org_b_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Studio Beta", "slug": "studio-beta"},
        )
        assert org_b_res.status_code == 201

        # User B attempts to access Org A projects -> MUST BE FORBIDDEN (403 or 404)
        denied_projects = await client.get(f"/api/v1/organizations/{org_a_id}/projects")
        assert denied_projects.status_code in [403, 404]

        # User B attempts to access Org A specific project -> MUST BE FORBIDDEN (403 or 404)
        denied_proj = await client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_id}")
        assert denied_proj.status_code in [403, 404]


@pytest.mark.asyncio
async def test_last_owner_protection():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User
        res = await client.post(
            "/api/v1/users",
            json={
                "name": "Sole Owner",
                "email": "sole_owner@studio.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 201
        cookie = res.cookies.get("clearcut_session")
        assert cookie is not None
        client.cookies.set("clearcut_session", cookie)

        # Create Org
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Single Owner Studio", "slug": "single-owner-studio"},
        )
        assert org_res.status_code == 201
        org_id = org_res.json()["data"]["orgId"]

        # Get memberships
        memberships_res = await client.get(f"/api/v1/organizations/{org_id}/memberships")
        assert memberships_res.status_code == 200
        membership_id = memberships_res.json()["data"][0]["membershipId"]

        # Try to demote the last active owner -> MUST FAIL 400
        demote_res = await client.post(
            f"/api/v1/organizations/{org_id}/memberships/{membership_id}:changeRole",
            json={"role": "reviewer"},
        )
        assert demote_res.status_code == 400
        assert demote_res.json()["error"]["code"] == "validation_failed"
        assert "last active owner" in demote_res.json()["error"]["message"].lower()
        assert demote_res.headers["x-request-id"]

        # Try to deactivate the last active owner -> MUST FAIL 400
        deact_res = await client.post(
            f"/api/v1/organizations/{org_id}/memberships/{membership_id}:deactivate",
        )
        assert deact_res.status_code == 400
        assert deact_res.json()["error"]["code"] == "validation_failed"
        assert "last active owner" in deact_res.json()["error"]["message"].lower()
        assert deact_res.headers["x-request-id"]


@pytest.mark.asyncio
async def test_invitation_lifecycle():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User 1 registers and creates org
        res1 = await client.post(
            "/api/v1/users",
            json={
                "name": "Inviter User",
                "email": "inviter@studio.com",
                "password": "Password123!",
            },
        )
        cookie1 = res1.cookies.get("clearcut_session")
        assert cookie1 is not None
        client.cookies.set("clearcut_session", cookie1)

        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Invite Studio", "slug": "invite-studio"},
        )
        org_id = org_res.json()["data"]["orgId"]

        # Invite user 2
        invite_res = await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "invitee@studio.com", "role": "reviewer"},
        )
        assert invite_res.status_code == 201
        token = invite_res.json()["data"]["token"]

        # User 2 registers
        res2 = await client.post(
            "/api/v1/users",
            json={
                "name": "Invitee User",
                "email": "invitee@studio.com",
                "password": "Password123!",
            },
        )
        cookie2 = res2.cookies.get("clearcut_session")
        assert cookie2 is not None
        client.cookies.set("clearcut_session", cookie2)

        # User 2 accepts invitation
        accept_res = await client.post(f"/api/v1/invitations/{token}:accept")
        assert accept_res.status_code == 200
        assert accept_res.json()["data"]["role"] == "reviewer"

        # User 2 can now access organization projects
        projects_res = await client.get(f"/api/v1/organizations/{org_id}/projects")
        assert projects_res.status_code == 200


@pytest.mark.asyncio
async def test_project_production_details_round_trip_and_legacy_create_compatibility():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Production Owner",
                "email": "production-owner@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Production Studio", "slug": "production-studio"},
        )
        org_id = organization.json()["data"]["orgId"]
        details = {
            "title": "Signal Check",
            "description": "Legacy compatible note",
            "productionType": "Feature film",
            "productionStage": "Pre-production",
            "jurisdiction": "California, United States",
            "targetLockDate": "2026-10-15",
            "reviewBrief": "Review named products and locations for unresolved evidence needs.",
        }
        created = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json=details,
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["data"]["projectId"]
        loaded = await client.get(f"/api/v1/organizations/{org_id}/projects/{project_id}")
        listed = await client.get(f"/api/v1/organizations/{org_id}/projects")

        assert loaded.status_code == 200, loaded.text
        for field, value in details.items():
            assert created.json()["data"][field] == value
            assert loaded.json()["data"][field] == value
        created_data = {**created.json()["data"]}
        loaded_data = {**loaded.json()["data"]}
        created_data.pop("createdAt")
        loaded_data.pop("createdAt")
        assert loaded_data == created_data
        assert (
            next(
                project for project in listed.json()["data"] if project["projectId"] == project_id
            )["productionType"]
            == "Feature film"
        )

        legacy = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Legacy Project"},
        )
        assert legacy.status_code == 201, legacy.text
        for field in (
            "productionType",
            "productionStage",
            "jurisdiction",
            "targetLockDate",
            "reviewBrief",
        ):
            assert legacy.json()["data"][field] is None


@pytest.mark.asyncio
async def test_project_repository_list_preserves_production_details() -> None:
    from datetime import date
    from uuid import UUID, uuid4

    from clearcut.database import session_scope
    from clearcut.projects.adapters.sql_repository import SqlProjectRepository
    from clearcut.projects.domain.models import Project

    await init_and_seed_db()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Repository Owner",
                "email": f"repository-owner-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Repository Studio", "slug": f"repository-{uuid4().hex[:8]}"},
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])

    project = Project.create(
        org_id=org_id,
        title="Repository details",
        production_type="Feature film",
        production_stage="Pre-production",
        jurisdiction="California, United States",
        target_lock_date=date(2026, 10, 15),
        review_brief="Preserve canonical fields across repository listing.",
    )
    async with session_scope() as session:
        repository = SqlProjectRepository(session)
        await repository.create_project(project)
        listed = await repository.list_projects(project.org_id)

    loaded = next(item for item in listed if item.project_id == project.project_id)
    assert loaded.production_type == project.production_type
    assert loaded.production_stage == project.production_stage
    assert loaded.jurisdiction == project.jurisdiction
    assert loaded.target_lock_date == project.target_lock_date
    assert loaded.review_brief == project.review_brief



@pytest.mark.asyncio
async def test_owner_can_replace_reviewer_project_grants_through_http_boundary() -> None:
    from uuid import uuid4

    await init_and_seed_db()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        owner_email = f"grant-owner-{uuid4().hex}@example.com"
        reviewer_email = f"grant-reviewer-{uuid4().hex}@example.com"
        owner_registration = await client.post(
            "/api/v1/users",
            json={"name": "Grant Owner", "email": owner_email, "password": "Password123!"},
        )
        owner_cookie = owner_registration.cookies.get("clearcut_session")
        assert owner_cookie is not None
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Grant Studio", "slug": f"grant-studio-{uuid4().hex[:8]}"},
        )
        org_id = organization.json()["data"]["orgId"]
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Scoped Project"},
        )
        project_id = project.json()["data"]["projectId"]
        invitation = await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": reviewer_email, "role": "reviewer"},
        )
        token = invitation.json()["data"]["token"]

        reviewer_registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Grant Reviewer",
                "email": reviewer_email,
                "password": "Password123!",
            },
        )
        reviewer_cookie = reviewer_registration.cookies.get("clearcut_session")
        assert reviewer_cookie is not None
        accepted = await client.post(f"/api/v1/invitations/{token}:accept")
        reviewer_membership_id = accepted.json()["data"]["membershipId"]

        import sqlalchemy as sa
        from clearcut.database import session_scope

        async with session_scope() as session:
            before = await session.execute(
                sa.text(
                    "SELECT count(*) FROM project_grants "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND membership_id = :membership_id"
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "membership_id": reviewer_membership_id,
                },
            )
            assert before.scalar_one() == 0

        client.cookies.set("clearcut_session", owner_cookie)
        granted = await client.post(
            f"/api/v1/organizations/{org_id}/memberships/{reviewer_membership_id}:changeProjectGrant",
            json={"projectIds": [project_id]},
        )
        assert granted.status_code == 200, granted.text
        assert granted.json()["data"]["projectGrants"] == [project_id]

        listed_memberships = await client.get(
            f"/api/v1/organizations/{org_id}/memberships"
        )
        assert listed_memberships.status_code == 200, listed_memberships.text
        reviewer_membership = next(
            membership
            for membership in listed_memberships.json()["data"]
            if membership["membershipId"] == reviewer_membership_id
        )
        assert reviewer_membership["projectGrants"] == [project_id]

        async with session_scope() as session:
            after = await session.execute(
                sa.text(
                    "SELECT count(*) FROM project_grants "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND membership_id = :membership_id"
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "membership_id": reviewer_membership_id,
                },
            )
            assert after.scalar_one() == 1



@pytest.mark.asyncio
async def test_new_organization_is_born_with_exactly_one_active_governing_binding():
    """A freshly created org must be immediately usable for detection.

    Detection, research, and rescan all refuse to run unless the org holds
    exactly one active protected configuration. Regression guard: the create
    endpoint once inserted only the org and owner, leaving every new org unable
    to complete a first pass until a binding was inserted by hand.
    """
    import sqlalchemy as sa
    from clearcut.database import session_scope

    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        registration = await client.post(
            "/api/v1/users",
            json={"name": "Owner", "email": "owner@borngoverned.example.com", "password": "Password123!"},
        )
        assert registration.status_code == 201
        client.cookies.set("clearcut_session", registration.cookies.get("clearcut_session"))

        created = await client.post(
            "/api/v1/organizations",
            json={"name": "Born Governed", "slug": "born-governed"},
        )
        assert created.status_code == 201, created.text
        org_id = created.json()["data"]["orgId"]

        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT policy_version, prompt_version FROM protected_configurations "
                        "WHERE org_id = :org_id AND lifecycle = 'active'"
                    ),
                    {"org_id": org_id},
                )
            ).mappings().all()

    assert len(rows) == 1, "a new org must have exactly one active governing binding"
    assert rows[0]["policy_version"]
    assert rows[0]["prompt_version"]
