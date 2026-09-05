from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_SRC = ROOT / "apps" / "web" / "src"

PROHIBITED = {
    "runtime import": 'import "./runtime.js"',
    "hash routing": "window.location.hash",
    "test fixture import": "tests/fixtures",
    "domain local storage": "clearcut-flow-state",
}


def test_no_legacy_runtime_file():
    runtime_js = WEB_SRC / "runtime.js"
    assert not runtime_js.exists(), "apps/web/src/runtime.js must not exist in production tree"


def test_no_prohibited_runtime_patterns_in_web_source():
    assert WEB_SRC.exists(), "apps/web/src directory must exist"

    source_files = (
        list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx")) + list(WEB_SRC.rglob("*.js"))
    )
    assert len(source_files) > 0, "Expected web source files to scan"

    violations = []
    for file_path in source_files:
        content = file_path.read_text(encoding="utf-8")
        rel_path = file_path.relative_to(ROOT)

        if "runtime.js" in content:
            violations.append(f"{rel_path}: references runtime.js")

        for name, pattern in PROHIBITED.items():
            if pattern in content:
                violations.append(f"{rel_path}: prohibited pattern '{name}' ({pattern})")

    assert not violations, "Found prohibited legacy runtime patterns in web source:\n" + "\n".join(
        violations
    )


def test_playwright_matrix_preserves_cross_engine_responsive_coverage():
    config = (ROOT / "apps" / "web" / "playwright.config.ts").read_text(encoding="utf-8")

    expected_projects = {
        'name: "chromium-desktop-1440"': 'devices["Desktop Chrome"]',
        'name: "firefox-desktop-1024"': 'devices["Desktop Firefox"]',
        'name: "webkit-tablet-768"': 'devices["Desktop Safari"]',
        'name: "mobile-375"': 'devices["iPhone 13"]',
    }
    missing = [
        f"{project} with {device}"
        for project, device in expected_projects.items()
        if project not in config or device not in config
    ]

    assert not missing, "Playwright cross-engine matrix regressions:\n" + "\n".join(missing)
    assert "workers: 1" in config, (
        "Playwright cross-engine execution must remain serial because the matrix shares one "
        "SQLite database and API worker"
    )



def test_evidence_drawer_never_invents_fallback_sources():
    drawer = (
        WEB_SRC / "features" / "clearance" / "EvidenceDrawer.tsx"
    ).read_text(encoding="utf-8")

    fabricated_sources = (
        "USPTO Trademark Electronic Search System",
        "California Secretary of State Business Search",
    )
    assert not [source for source in fabricated_sources if source in drawer]



def test_evidence_drawer_never_upgrades_missing_provenance_metadata():
    drawer = (
        WEB_SRC / "features" / "clearance" / "EvidenceDrawer.tsx"
    ).read_text(encoding="utf-8")

    invented_defaults = (
        'claim.stance || "supporting"',
        'claim.authority || "Primary Statutory Registry"',
        'claim.publisher || "Official Source"',
    )
    assert not [default for default in invented_defaults if default in drawer]



def test_comment_thread_never_fabricates_persisted_comments_or_identity():
    thread = (
        WEB_SRC / "features" / "collaboration" / "CommentThread.tsx"
    ).read_text(encoding="utf-8")

    fabricated_comment_markers = (
        "Sarah Chen",
        "USPTO Class 09",
        "Date.now()",
        "Jamie Park",
    )
    assert not [marker for marker in fabricated_comment_markers if marker in thread]



def test_referral_card_never_claims_browser_local_completion():
    card = (
        WEB_SRC / "features" / "collaboration" / "ReferralCard.tsx"
    ).read_text(encoding="utf-8")

    local_success_markers = (
        'setStatus("referred")',
        'setStatus("acknowledged")',
        'useState<"idle" | "referred" | "acknowledged">',
    )
    assert not [marker for marker in local_success_markers if marker in card]



def test_workspace_never_substitutes_the_first_item_for_direct_identity():
    workspace = (
        WEB_SRC / "routes" / "o" / "$orgSlug" / "projects" / "$projectId" / "workspace.tsx"
    ).read_text(encoding="utf-8")

    assert "loadedItems[0]" not in workspace



def test_clearance_item_routes_use_shared_authoritative_queries():
    routes = (
        WEB_SRC / "routes" / "o" / "$orgSlug" / "projects" / "$projectId" / "items"
    )
    item_list = (routes / "index.tsx").read_text(encoding="utf-8")
    item_detail = (routes / "$itemId.tsx").read_text(encoding="utf-8")

    assert "clearanceItemsQueryOptions" in item_list
    assert "api.listClearanceItems" not in item_list
    assert "clearanceItemDetailQueryOptions" in item_detail
    assert "api.getClearanceItem" not in item_detail



def test_workspace_and_evidence_components_use_generated_item_identity():
    workspace = (
        WEB_SRC / "routes" / "o" / "$orgSlug" / "projects" / "$projectId" / "workspace.tsx"
    ).read_text(encoding="utf-8")
    card = (
        WEB_SRC / "features" / "clearance" / "ClearanceItemCard.tsx"
    ).read_text(encoding="utf-8")
    drawer = (
        WEB_SRC / "features" / "clearance" / "EvidenceDrawer.tsx"
    ).read_text(encoding="utf-8")

    assert "clearanceItemsQueryOptions" in workspace
    assert "clearanceItemDetailQueryOptions" in workspace
    assert "as unknown as ClearanceItem[]" not in workspace
    assert 'type { ClearanceItem } from "@clearcut/contracts"' in card
    assert 'type { ClearanceItemDetail } from "@clearcut/contracts"' in drawer
    for legacy_field in ("claim_id", "source_title", "source_url", "retrieved_at"):
        assert legacy_field not in drawer



def test_item_detail_wires_comment_form_to_authoritative_mutation():
    detail = (
        WEB_SRC
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "items"
        / "$itemId.tsx"
    ).read_text(encoding="utf-8")

    assert "addCommentMutationOptions" in detail
    assert "onAddComment=" in detail



def test_item_detail_wires_referral_form_to_authoritative_mutation():
    detail = (
        WEB_SRC
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "items"
        / "$itemId.tsx"
    ).read_text(encoding="utf-8")

    assert "referClearanceItemMutationOptions" in detail
    assert "referrals={item.referrals}" in detail
    assert "onRefer={handleRefer}" in detail



def test_item_detail_wires_referral_acknowledgement_to_authoritative_mutation():
    detail = (
        WEB_SRC
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "items"
        / "$itemId.tsx"
    ).read_text(encoding="utf-8")

    assert "acknowledgeReferralMutationOptions" in detail
    assert "onAcknowledge={handleAcknowledgeReferral}" in detail



def test_item_detail_wires_persisted_comment_history_reply_and_revision():
    detail = (
        WEB_SRC
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "items"
        / "$itemId.tsx"
    ).read_text(encoding="utf-8")

    assert "replyToCommentMutationOptions" in detail
    assert "reviseCommentMutationOptions" in detail
    assert "comments={item.comments}" in detail
    assert "onReply={handleReplyToComment}" in detail
    assert "onRevise={handleReviseComment}" in detail
    assert "const comments = item.comments.map" not in detail



def test_item_detail_wires_assignment_and_disposition_to_authoritative_mutations():
    detail = (
        WEB_SRC
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "items"
        / "$itemId.tsx"
    ).read_text(encoding="utf-8")

    assert "ItemGovernanceControls" in detail
    assert "assignClearanceItemMutationOptions" in detail
    assert "setDispositionMutationOptions" in detail
    assert "onAssign={handleAssign}" in detail
    assert "onSetDisposition={handleSetDisposition}" in detail



def test_workspace_supplies_modal_focus_return_contract():
    workspace = (
        WEB_SRC / "routes" / "o" / "$orgSlug" / "projects" / "$projectId" / "workspace.tsx"
    ).read_text(encoding="utf-8")

    assert "returnFocusRef={uploadButtonRef}" in workspace
    assert "successFocusRef={workspaceHeadingRef}" in workspace
    assert "ref={uploadButtonRef}" in workspace
    assert "ref={workspaceHeadingRef}" in workspace



def test_org_layout_does_not_duplicate_app_shell_outlet():
    route = (WEB_SRC / "routes" / "o" / "$orgSlug" / "route.tsx").read_text(encoding="utf-8")

    assert "<AppShell orgSlug={orgSlug} />" in route
    assert "<Outlet" not in route


def test_monitoring_cadence_uses_canonical_typed_values():
    selector = (
        WEB_SRC / "features" / "monitoring" / "CadenceSelector.tsx"
    ).read_text(encoding="utf-8")
    route = (
        WEB_SRC / "routes" / "o" / "$orgSlug" / "projects" / "$projectId" / "watch.tsx"
    ).read_text(encoding="utf-8")

    assert 'export type MonitoringCadence = "daily" | "weekly" | "biweekly" | "monthly"' in selector
    assert 'id: "bi-weekly"' not in selector
    assert "useState<MonitoringCadence>" in route


def test_team_invitation_uses_only_canonical_user_roles():
    route = (WEB_SRC / "routes" / "o" / "$orgSlug" / "team.tsx").read_text(encoding="utf-8")

    assert "type UserRole" in route
    assert "useState<UserRole>" in route
    assert '<option value="producer">' not in route
    assert '<option value="counsel">' not in route


def test_task_11_has_deterministic_provider_free_evidence_browser_coverage():
    workspace_spec = ROOT / "apps" / "web" / "tests" / "e2e" / "evidence-workspace.spec.ts"
    access_spec = ROOT / "apps" / "web" / "tests" / "e2e" / "evidence-access.spec.ts"
    support_api = (ROOT / "apps" / "web" / "tests" / "support" / "e2e_api.py").read_text(
        encoding="utf-8"
    )

    assert workspace_spec.exists(), "Task 11 requires API-connected evidence workspace coverage"
    assert access_spec.exists(), "Task 11 requires evidence authorization and access coverage"
    assert '"/e2e/organizations/{org_id}/projects/{project_id}/evidence-fixture"' in support_api
    assert "research_provider" not in support_api
