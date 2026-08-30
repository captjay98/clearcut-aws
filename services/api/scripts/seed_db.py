"""Seed PostgreSQL database with canonical ClearCut project dataset."""
import asyncio
import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from clearcut.database import engine, is_sqlite

ORG_ID = uuid.UUID("018f0000-0000-7000-8000-000000000001")
PROJECT_ID = uuid.UUID("018f0000-0000-7000-8000-000000000101")
SCRIPT_ID = uuid.UUID("018f0000-0000-7000-8000-000000000201")
VERSION_ID = uuid.UUID("018f0000-0000-7000-8000-000000000301")

def fmt_id(val):
    if val is None:
        return None
    return str(val) if is_sqlite else val

def fmt_dt(val):
    if val is None:
        return None
    return val.isoformat() if is_sqlite else val

USERS = [
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000000011"), "name": "Jamie Park", "email": "jamie@northlight.example", "role": "Owner"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000000012"), "name": "Mara Voss", "email": "mara@northlight.example", "role": "Reviewer"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000000013"), "name": "Theo Grant", "email": "theo@northlight.example", "role": "Editor"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000000014"), "name": "Eli Chen", "email": "eli@northlight.example", "role": "Reviewer"},
]

SCENES_DATA = [
    {
        "number": 3,
        "slug": "INT. VELEZ CAMERA SHOP — DUSK",
        "page": 2,
        "lines": [
            {"type": "action", "text": "Dust hangs in the last bar of window light."},
            {"type": "action", "text": "MINA VELEZ, 31, turns the lock and studies the room as if it belongs to someone else.", "flag": "CC-102"},
            {"type": "action", "text": "She lifts the Vega Camera from a glass case.", "flag": "CC-101"},
            {"type": "character", "text": "MINA"},
            {"type": "dialogue", "text": "We only borrow the light."},
        ],
    },
    {
        "number": 7,
        "slug": "EXT. SUNSET TOWER — NIGHT",
        "page": 5,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "The crew unloads beneath the Sunset Tower marquee.", "flag": "CC-103"},
            {"type": "action", "text": 'A radio host announces "Blue Monday" over the PA. Mina reaches for the dial.', "flag": "CC-104"},
        ],
    },
    {
        "number": 9,
        "slug": "INT. CORNER DINER — NIGHT",
        "page": 7,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "A trucker counts coins onto the counter."},
            {"type": "character", "text": "TRUCKER"},
            {"type": "dialogue", "text": "Keep the change.", "flag": "CC-105"},
        ],
    },
    {
        "number": 12,
        "slug": "EXT. HARBOR CHECKPOINT — DAY",
        "page": 9,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "A polished Northstar badge catches the light as the officer waves the truck through.", "flag": "CC-106"},
        ],
    },
    {
        "number": 14,
        "slug": "EXT. BOARDWALK — DUSK",
        "page": 11,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "A red bicycle silhouette leans against the rail.", "flag": "CC-107"},
        ],
    },
    {
        "number": 16,
        "slug": "INT. PROJECTION BOOTH — NIGHT",
        "page": 13,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "A faded Glass House poster watches from the wall.", "flag": "CC-108"},
        ],
    },
    {
        "number": 18,
        "slug": "INT. CLINIC CORRIDOR — DAY",
        "page": 15,
        "pageBreakBefore": True,
        "lines": [
            {"type": "action", "text": "DR. LENORA SHAW reviews a chart.", "flag": "CC-109"},
            {"type": "character", "text": "DR. SHAW"},
            {"type": "dialogue", "text": "Her relapse began after she left the East Mercer clinic, room 214.", "flag": "CC-110", "rewritten": "She struggled again after she left treatment."},
        ],
    },
]

ITEMS = [
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001101"), "flag": "CC-101", "term": "Vega Camera", "category": "Brands & trademarks", "status": "Needs your call", "workflow": "needs_call", "research": "completed", "assignee": "Mara Voss"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001102"), "flag": "CC-102", "term": "Mina Velez", "category": "People & likeness", "status": "Needs your call", "workflow": "needs_call", "research": "completed", "assignee": "Theo Grant"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001103"), "flag": "CC-103", "term": "Sunset Tower", "category": "Locations & property", "status": "Sources disagree", "workflow": "conflict", "research": "completed", "assignee": "Mara Voss"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001104"), "flag": "CC-104", "term": "Blue Monday", "category": "Music & lyrics", "status": "With specialist", "workflow": "referred", "research": "completed", "assignee": "Eli Chen"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001105"), "flag": "CC-105", "term": "Keep the change", "category": "Dialogue & quotations", "status": "Could not verify", "workflow": "unverified", "research": "completed", "assignee": "Theo Grant"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001106"), "flag": "CC-106", "term": "Northstar badge", "category": "Organizations & insignia", "status": "Verified", "workflow": "verified", "research": "completed", "assignee": "Mara Voss"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001107"), "flag": "CC-107", "term": "Red bicycle silhouette", "category": "Products & trade dress", "status": "Needs your call", "workflow": "needs_call", "research": "completed", "assignee": "Theo Grant"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001108"), "flag": "CC-108", "term": "Glass House poster", "category": "Artwork & media", "status": "Verified", "workflow": "verified", "research": "completed", "assignee": "Mara Voss"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001109"), "flag": "CC-109", "term": "Dr. Lenora Shaw", "category": "Names & characters", "status": "Needs your call", "workflow": "needs_call", "research": "completed", "assignee": "Eli Chen"},
    {"id": uuid.UUID("018f0000-0000-7000-8000-000000001110"), "flag": "CC-110", "term": "patient relapse history", "category": "Privacy & sensitive facts", "status": "Must fix", "workflow": "blocked", "research": "completed", "assignee": "Mara Voss"},
]

SOURCES = [
    {"num": 1, "item_idx": 0, "title": "USPTO TSDR record 8850142", "auth": "Primary registry", "stance": "supports", "claim": "VEGA registered in class 009 for professional motion-picture camera equipment; status live."},
    {"num": 2, "item_idx": 0, "title": "USPTO assignment history, reel 7741", "auth": "Primary registry", "stance": "context", "claim": "Ownership assigned to Vega Optics LLC in 2019; no later transfer recorded."},
    {"num": 3, "item_idx": 0, "title": "Trade article, Camera Quarterly", "auth": "Secondary", "stance": "conflicts", "claim": "Describes the VEGA mark as abandoned after the 2021 product line was retired."},
    {"num": 4, "item_idx": 0, "title": "Vega Optics product catalogue", "auth": "Secondary", "stance": "context", "claim": "Mark still used in commerce on current service parts."},
    {"num": 5, "item_idx": 1, "title": "Licensed talent directory", "auth": "Secondary", "stance": "supports", "claim": "No exact public-figure match for the character name."},
    {"num": 6, "item_idx": 1, "title": "Public records index, two partial matches", "auth": "Secondary", "stance": "context", "claim": "Two individuals share the surname in the depicted region; neither is a public figure."},
    {"num": 7, "item_idx": 1, "title": "Screen credits database", "auth": "Secondary", "stance": "context", "claim": "No prior screen character of this name in the last twenty years."},
    {"num": 8, "item_idx": 2, "title": "Property release archive, exterior terms", "auth": "Mixed", "stance": "supports", "claim": "Editorial exterior photography permitted; commercial set dressing not addressed."},
    {"num": 9, "item_idx": 2, "title": "Venue filming policy, revision 4", "auth": "Primary", "stance": "conflicts", "claim": "Requires written consent for any commercial dressing of the marquee."},
    {"num": 10, "item_idx": 2, "title": "Municipal filming guidance, §6", "auth": "Primary", "stance": "conflicts", "claim": "Treats public-right-of-way exteriors as permitted with a location permit alone."},
    {"num": 11, "item_idx": 2, "title": "Prior production location log", "auth": "Secondary", "stance": "context", "claim": "Two features shot the same exterior under permit in the past five years."},
    {"num": 12, "item_idx": 3, "title": "PRO repertory search, title query", "auth": "Primary", "stance": "supports", "claim": "Multiple registered compositions share the title; none matched conclusively."},
    {"num": 13, "item_idx": 3, "title": "Second PRO repertory, writer query", "auth": "Primary", "stance": "conflicts", "claim": "Returns a different candidate work than the title query."},
    {"num": 14, "item_idx": 3, "title": "Sound-recording rights index", "auth": "Secondary", "stance": "context", "claim": "Recording and composition rights sit with different owners for two candidates."},
    {"num": 15, "item_idx": 3, "title": "Lyric fragment concordance", "auth": "Unavailable", "stance": "context", "claim": "Fragment too short to attribute; search bounded without a result."},
    {"num": 16, "item_idx": 4, "title": "Quotation corpus search", "auth": "Unavailable", "stance": "supports", "claim": "No unique attributable source after a bounded search."},
    {"num": 17, "item_idx": 4, "title": "Idiom usage index", "auth": "Secondary", "stance": "context", "claim": "Phrase recorded in common usage well before any candidate source."},
    {"num": 18, "item_idx": 5, "title": "State insignia code §14.2", "auth": "Primary", "stance": "supports", "claim": "Protected seal specifies five points and a distinct motto ring."},
    {"num": 19, "item_idx": 5, "title": "State seal reference image", "auth": "Primary", "stance": "supports", "claim": "Depicted seven-point badge differs materially from the protected seal."},
    {"num": 20, "item_idx": 5, "title": "Prop house design provenance", "auth": "Secondary", "stance": "context", "claim": "Badge is an original prop design commissioned for the production."},
    {"num": 21, "item_idx": 6, "title": "Visual similarity index", "auth": "Secondary", "stance": "supports", "claim": "Silhouette is a common shape with no distinctive protected form."},
    {"num": 22, "item_idx": 6, "title": "Design registry, frame decal", "auth": "Primary registry", "stance": "context", "claim": "A registered decal design resembles the one visible on the frame."},
    {"num": 23, "item_idx": 6, "title": "Manufacturer catalogue, 2024 range", "auth": "Secondary", "stance": "context", "claim": "Decal appears on a current production model."},
    {"num": 24, "item_idx": 7, "title": "Copyright Office record PA000224189", "auth": "Primary registry", "stance": "supports", "claim": "Poster artwork registered to Halcyon Archive LLC."},
    {"num": 25, "item_idx": 7, "title": "Copyright Office renewal record", "auth": "Primary registry", "stance": "supports", "claim": "Registration renewed; term runs well past the production window."},
    {"num": 26, "item_idx": 7, "title": "Halcyon Archive licensing terms", "auth": "Primary", "stance": "context", "claim": "Publishes a standard set-dressing licence for archival poster art."},
    {"num": 27, "item_idx": 7, "title": "Auction catalogue provenance note", "auth": "Secondary", "stance": "context", "claim": "Confirms the artist attribution recorded in the registration."},
    {"num": 28, "item_idx": 8, "title": "Character and name corpus", "auth": "Mixed", "stance": "supports", "claim": "No exact fictional-character match in the corpus."},
    {"num": 29, "item_idx": 8, "title": "Professional licensing register", "auth": "Primary", "stance": "conflicts", "claim": "A licensed clinician of the same name practises in the depicted specialty."},
    {"num": 30, "item_idx": 8, "title": "Regional name frequency study", "auth": "Secondary", "stance": "context", "claim": "Surname is uncommon in the region, raising identifiability."},
    {"num": 31, "item_idx": 8, "title": "Published news archive", "auth": "Secondary", "stance": "context", "claim": "No reporting links that clinician to the depicted events."},
    {"num": 32, "item_idx": 9, "title": "ClearCut privacy policy P-12", "auth": "Policy", "stance": "supports", "claim": "Health history combined with a named location may identify a real person."},
    {"num": 33, "item_idx": 9, "title": "Named facility register", "auth": "Primary", "stance": "supports", "claim": "The clinic named in the passage exists at the stated location."},
    {"num": 34, "item_idx": 9, "title": "Health-information handling guidance", "auth": "Primary", "stance": "context", "claim": "Room-level detail is treated as directly identifying in guidance."},
    {"num": 35, "item_idx": 9, "title": "Broadcast standards note, depiction", "auth": "Secondary", "stance": "context", "claim": "Recommends removing facility identifiers from dramatised treatment."},
    {"num": 36, "item_idx": 9, "title": "Prior rewrite precedent log", "auth": "Secondary", "stance": "context", "claim": "Comparable passages cleared after removing the location detail."},
    {"num": 37, "item_idx": 9, "title": "Facility press office statement", "auth": "Primary", "stance": "context", "claim": "Declines to consent to identification in dramatic contexts."},
    {"num": 38, "item_idx": 9, "title": "Insurer clearance checklist, item 9", "auth": "Secondary", "stance": "context", "claim": "Lists identifiable health detail among standard pre-delivery removals."},
]

async def seed():
    now = datetime.now(UTC)
    async with engine.begin() as conn:
        print("Cleaning previous seed data...")
        if is_sqlite:
            await conn.execute(sa.text("DELETE FROM organizations;"))
            await conn.execute(sa.text("DELETE FROM users;"))
        else:
            await conn.execute(sa.text("TRUNCATE organizations CASCADE;"))
            await conn.execute(sa.text("TRUNCATE users CASCADE;"))

        print("Seeding Users...")
        for u in USERS:
            await conn.execute(
                sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
                {"id": fmt_id(u["id"]), "email": u["email"], "created_at": fmt_dt(now)},
            )

        print("Seeding Organization...")
        await conn.execute(
            sa.text("INSERT INTO organizations (id, name, slug, created_at) VALUES (:id, :name, :slug, :created_at)"),
            {"id": fmt_id(ORG_ID), "name": "Northlight Pictures", "slug": "northlight", "created_at": fmt_dt(now)},
        )

        print("Seeding Memberships...")
        for u in USERS:
            await conn.execute(
                sa.text("INSERT INTO memberships (id, org_id, user_id, role, status, created_at) VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"),
                {"id": fmt_id(uuid.uuid4()), "org_id": fmt_id(ORG_ID), "user_id": fmt_id(u["id"]), "role": u["role"], "created_at": fmt_dt(now)},
            )

        print("Seeding Project...")
        await conn.execute(
            sa.text("INSERT INTO projects (id, org_id, title, description, created_at) VALUES (:id, :org_id, :title, :description, :created_at)"),
            {"id": fmt_id(PROJECT_ID), "org_id": fmt_id(ORG_ID), "title": "Borrowed Light", "description": "Independent feature screenplay pre-clearance workspace", "created_at": fmt_dt(now)},
        )

        print("Seeding Script & Script Version...")
        await conn.execute(
            sa.text("INSERT INTO scripts (id, org_id, project_id, title, created_at) VALUES (:id, :org_id, :project_id, :title, :created_at)"),
            {"id": fmt_id(SCRIPT_ID), "org_id": fmt_id(ORG_ID), "project_id": fmt_id(PROJECT_ID), "title": "Borrowed Light", "created_at": fmt_dt(now)},
        )
        await conn.execute(
            sa.text("INSERT INTO script_versions (id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) VALUES (:id, :script_id, :org_id, :project_id, 1, '9c7a23d08e41', '1.0.0', :created_at)"),
            {"id": fmt_id(VERSION_ID), "script_id": fmt_id(SCRIPT_ID), "org_id": fmt_id(ORG_ID), "project_id": fmt_id(PROJECT_ID), "created_at": fmt_dt(now)},
        )

        print("Seeding All Screenplay Scenes & Elements...")
        element_ordinal = 1
        flag_to_element_id = {}

        for scene in SCENES_DATA:
            # Seed scene heading element
            scene_heading_id = uuid.uuid4()
            await conn.execute(
                sa.text("""
                    INSERT INTO script_elements (id, version_id, ordinal, element_type, text, scene_number, page_number)
                    VALUES (:id, :version_id, :ordinal, 'scene_heading', :text, :scene, :page)
                """),
                {
                    "id": fmt_id(scene_heading_id),
                    "version_id": fmt_id(VERSION_ID),
                    "ordinal": element_ordinal,
                    "text": scene["slug"],
                    "scene": scene["number"],
                    "page": scene["page"],
                },
            )
            element_ordinal += 1

            for line in scene["lines"]:
                line_elem_id = uuid.uuid4()
                await conn.execute(
                    sa.text("""
                        INSERT INTO script_elements (id, version_id, ordinal, element_type, text, scene_number, page_number)
                        VALUES (:id, :version_id, :ordinal, :element_type, :text, :scene, :page)
                    """),
                    {
                        "id": fmt_id(line_elem_id),
                        "version_id": fmt_id(VERSION_ID),
                        "ordinal": element_ordinal,
                        "element_type": line["type"],
                        "text": line["text"],
                        "scene": scene["number"],
                        "page": scene["page"],
                    },
                )
                if "flag" in line:
                    flag_to_element_id[line["flag"]] = line_elem_id
                    span_id = uuid.uuid4()
                    await conn.execute(
                        sa.text("""
                            INSERT INTO element_spans (id, element_id, start_char, end_char, text, tag)
                            VALUES (:id, :element_id, 0, :length, :text, :tag)
                        """),
                        {
                            "id": fmt_id(span_id),
                            "element_id": fmt_id(line_elem_id),
                            "length": len(line["text"]),
                            "text": line["text"],
                            "tag": line["flag"],
                        },
                    )
                element_ordinal += 1

        print("Seeding Clearance Items with Real Element Bindings...")
        for item in ITEMS:
            elem_id = flag_to_element_id.get(item["flag"], uuid.uuid4())
            assignee_user = next((u for u in USERS if u["name"] == item["assignee"]), USERS[1])

            await conn.execute(
                sa.text("""
                    INSERT INTO clearance_items (
                        id, org_id, project_id, script_id, version_id, element_id,
                        category, text, status, created_at, research_status, workflow_status, disposition_status, assigned_to_user_id
                    ) VALUES (
                        :id, :org_id, :project_id, :script_id, :version_id, :element_id,
                        :category, :text, :status, :created_at, :research_status, :workflow_status, 'undisposed', :assigned_to
                    )
                """),
                {
                    "id": fmt_id(item["id"]),
                    "org_id": fmt_id(ORG_ID),
                    "project_id": fmt_id(PROJECT_ID),
                    "script_id": fmt_id(SCRIPT_ID),
                    "version_id": fmt_id(VERSION_ID),
                    "element_id": fmt_id(elem_id),
                    "category": item["category"],
                    "text": item["term"],
                    "status": item["status"],
                    "created_at": fmt_dt(now),
                    "research_status": item["research"],
                    "workflow_status": item["workflow"],
                    "assigned_to": fmt_id(assignee_user["id"]),
                },
            )

            # Seed Research Run for this item
            run_id = uuid.uuid4()
            await conn.execute(
                sa.text("INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at) VALUES (:id, :org_id, :project_id, :item_id, 'completed', :created_at)"),
                {"id": fmt_id(run_id), "org_id": fmt_id(ORG_ID), "project_id": fmt_id(PROJECT_ID), "item_id": fmt_id(item["id"]), "created_at": fmt_dt(now)},
            )
            item["run_id"] = run_id

        print("Seeding Source Snapshots & Evidence Claims...")
        for s in SOURCES:
            target_item = ITEMS[s["item_idx"]]
            snap_id = uuid.uuid4()
            claim_id = uuid.uuid4()

            await conn.execute(
                sa.text("""
                    INSERT INTO source_snapshots (
                        id, org_id, project_id, item_id, run_id,
                        url, title, publisher, excerpt, origin, sha256_hash, retrieved_at
                    ) VALUES (
                        :id, :org_id, :project_id, :item_id, :run_id,
                        :url, :title, :publisher, :excerpt, 'parallel', :hash, :retrieved_at
                    )
                """),
                {
                    "id": fmt_id(snap_id),
                    "org_id": fmt_id(ORG_ID),
                    "project_id": fmt_id(PROJECT_ID),
                    "item_id": fmt_id(target_item["id"]),
                    "run_id": fmt_id(target_item["run_id"]),
                    "url": f"https://registry.example.gov/records/{s['num']}",
                    "title": s["title"],
                    "publisher": s["auth"],
                    "excerpt": s["claim"],
                    "hash": f"hash_{s['num']}_{uuid.uuid4().hex[:16]}",
                    "retrieved_at": fmt_dt(now),
                },
            )

            await conn.execute(
                sa.text("""
                    INSERT INTO evidence_claims (
                        id, org_id, project_id, item_id, snapshot_id,
                        stance, authority_tier, claim_text, provenance_excerpt, created_at
                    ) VALUES (
                        :id, :org_id, :project_id, :item_id, :snapshot_id,
                        :stance, :authority_tier, :claim_text, :provenance, :created_at
                    )
                """),
                {
                    "id": fmt_id(claim_id),
                    "org_id": fmt_id(ORG_ID),
                    "project_id": fmt_id(PROJECT_ID),
                    "item_id": fmt_id(target_item["id"]),
                    "snapshot_id": fmt_id(snap_id),
                    "stance": s["stance"],
                    "authority_tier": s["auth"],
                    "claim_text": s["claim"],
                    "provenance": s["title"],
                    "created_at": fmt_dt(now),
                },
            )

        print("Seeding Audit Events...")
        await conn.execute(
            sa.text("""
                INSERT INTO audit_events (
                    id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at
                ) VALUES (
                    :id, :org_id, :project_id, 'script.ingested', :actor_id, :target_id, 'script_version', :details, :created_at
                )
            """),
            {
                "id": fmt_id(uuid.uuid4()),
                "org_id": fmt_id(ORG_ID),
                "project_id": fmt_id(PROJECT_ID),
                "actor_id": fmt_id(USERS[0]["id"]),
                "target_id": fmt_id(VERSION_ID),
                "details": json.dumps({"version": "v1", "source": "FDX import"}),
                "created_at": fmt_dt(now),
            },
        )

    print("✨ Database seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
