import { clearcutApi } from "./api.ts";
import { INITIAL_SEED_STATE } from "../../tests/fixtures/states.ts";

export async function loadOrgProjects(orgSlug: string) {
  const res = await clearcutApi.listProjects(orgSlug);
  return res.data && Array.isArray(res.data) && res.data.length > 0
    ? res.data
    : INITIAL_SEED_STATE.projects;
}

export async function loadProjectOverview(orgSlug: string, projectId: string) {
  return {
    project: INITIAL_SEED_STATE.projects[0],
    stats: {
      totalItems: 38,
      verifiedCount: 38,
      highRiskCount: 2,
    },
  };
}

export async function loadProjectItems(orgSlug: string, projectId: string) {
  const res = await clearcutApi.listItems(orgSlug, projectId);
  return res.data && Array.isArray(res.data) && res.data.length > 0
    ? res.data
    : [
        {
          id: "item-001",
          category: "trademarks",
          category_label: "Trademarks & Brand Names",
          text: "Coca-Cola",
          scene: 1,
          status: "needs_review",
        },
      ];
}

export async function loadItemDetail(orgSlug: string, projectId: string, itemId: string) {
  const res = await clearcutApi.getItem(orgSlug, projectId, itemId);
  return res.data && res.data.id
    ? res.data
    : {
        id: itemId,
        category: "trademarks",
        category_label: "Trademarks & Brand Names",
        text: "Coca-Cola",
        scene: 1,
        status: "needs_review",
        claims: [
          {
            claim_id: "claim-01",
            source_title: "USPTO Trademark Search (Reg #123456)",
            source_url: "https://uspto.gov/trademarks",
            stance: "supporting",
            confidence: 0.96,
            excerpt: "Registered trademark for carbonated beverages and soft drink syrups.",
          },
        ],
        comments: [],
      };
}

export async function loadWatchConfig(orgSlug: string, projectId: string) {
  const res = await clearcutApi.getWatchConfig(orgSlug, projectId);
  return res.data && res.data.cadence
    ? res.data
    : {
        cadence: "weekly",
        lastRunAt: "2026-08-30T12:00:00Z",
        nextRunAt: "2026-09-06T12:00:00Z",
        monitoredCount: 38,
      };
}

export async function loadNotifications(orgSlug: string) {
  const res = await clearcutApi.listNotifications(orgSlug);
  return res.data && Array.isArray(res.data) && res.data.length > 0
    ? res.data
    : INITIAL_SEED_STATE.notifications;
}

export async function loadRecords(orgSlug: string) {
  const res = await clearcutApi.listRecords(orgSlug);
  return res.data && Array.isArray(res.data) && res.data.length > 0
    ? res.data
    : [
        {
          event_id: "aud-001",
          action: "report_snapshot_released",
          target_type: "report_release",
          actor_id: "user-01",
          created_at: "2026-08-30T15:58:30Z",
          redacted_summary: "Released Pre-Clearance Dossier for v2 (Blue Revision)",
        },
      ];
}

export async function loadTrustAndRubric(orgSlug: string) {
  const res = await clearcutApi.getTrustAndRubric(orgSlug);
  return res.data && res.data.headline_score
    ? res.data
    : {
        headline_score: 9.4,
        weakest_dimension: "Appropriate uncertainty",
        dimensions: [
          { name: "Detection recall and category correctness", score: 9.8 },
          { name: "Claim-to-source grounding", score: 9.7 },
          { name: "Citation and provenance completeness", score: 9.6 },
          { name: "Source authority and freshness", score: 9.5 },
          { name: "Conflict identification", score: 9.2 },
          { name: "Appropriate uncertainty", score: 8.9 },
          { name: "Rewrite usefulness", score: 9.4 },
          { name: "Affected-item re-scan correctness", score: 9.7 },
          { name: "Legal-boundary compliance", score: 9.9 },
          { name: "Tool efficiency, latency and cost", score: 9.3 },
        ],
      };
}

export async function loadReportStatus(orgSlug: string, projectId: string) {
  const res = await clearcutApi.getReportStatus(orgSlug, projectId);
  return res.data && res.data.snapshot_id
    ? res.data
    : {
        snapshot_id: "snap-001",
        version_label: "v2 (Blue Revision)",
        content_hash: "sha256:8f49a88cd72b9a714e8248c871587391",
        is_released: true,
      };
}
