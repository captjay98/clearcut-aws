import React, { useState } from "react";
import type {
  ClearanceItem,
  MonitoringPolicy,
  MonitoringRun,
  Project,
  ReportSnapshot,
  ScriptVersion,
  TrustEvaluation,
} from "@clearcut/contracts";
import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  Section,
  TabsBar,
  type TabItem,
  type Tone,
} from "../../components/ds";
import { humanizeCategory, humanizeStatus, statusTone } from "../clearance/itemPresentation";

/**
 * The clearance report rendered as a live, version-bound document.
 *
 * Every exhibit renders ONLY data supplied through its typed prop. Where an
 * exhibit's data is unavailable the exhibit renders an explicit "not available"
 * state — it never invents a source, a version, a hash, or a count. Evidence
 * provenance is mandatory here: a source row exists only because a cited
 * SourceSnapshot / EvidenceClaim was returned by the API and flattened by the
 * route.
 *
 * The seven-tab structure mirrors the report design:
 *   [A·Versions] [B·Flags] [C·Sources] [D·Project] [E·Trust] [Open items] [Binding]
 * The document is additive to the preview/generate/release/download controls;
 * it does not replace them.
 */

const LEGAL_DISCLAIMER =
  "A production record of what was checked, decided, and left open. It is not legal advice and does not certify clearance. Final legal judgement rests with counsel.";

const NOT_AVAILABLE = "Not available";

/** A source row for Exhibit C, flattened across every clearance item. */
export interface ReportSourceRow {
  /** Stable key: snapshotId scoped to the citing item so duplicates across items each render. */
  key: string;
  itemId: string;
  entityName: string;
  authorityTier: string;
  publisher: string;
  url: string;
  retrievedAt: string;
  excerpt: string;
  stance: string;
}

export interface ReportDocumentProps {
  /** Exhibit A — committed script versions and their revision stock. */
  versions: readonly ScriptVersion[];
  /** Exhibit B + Open-items — the full flags register. */
  items: readonly ClearanceItem[];
  /** Exhibit C — every retrieved source across all items, already flattened by the route. */
  sources: readonly ReportSourceRow[];
  /** True when per-item evidence aggregation has been attempted for every item. */
  sourcesComplete: boolean;
  /** Exhibit D — project details. */
  project: Project | null;
  /** Exhibit E — monitoring run history. */
  monitoringRuns: readonly MonitoringRun[];
  /** Exhibit E — monitoring cadence/policy at load time. */
  monitoringPolicy: MonitoringPolicy | null;
  /** Exhibit E — AI-trust evaluations. */
  trustEvaluations: readonly TrustEvaluation[];
  /** Version-binding table — the released/generated snapshot, when one exists. */
  snapshot: ReportSnapshot | null;
  /** True while exhibit data is still loading; suppresses premature empty states. */
  loading?: boolean;
}

type ExhibitTab = "a" | "b" | "c" | "d" | "e" | "open" | "binding";

function formatDateTime(value?: string | null): string {
  if (!value) return NOT_AVAILABLE;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDate(value?: string | null): string {
  if (!value) return NOT_AVAILABLE;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

/** Text cell that renders an explicit em dash when the value is absent. */
function textOrDash(value: string | number | null | undefined): React.ReactNode {
  if (value === null || value === undefined || value === "") {
    return <span className="muted">—</span>;
  }
  return String(value);
}

function stanceTone(stance: string): Tone {
  const normalized = stance.toLowerCase();
  if (normalized.includes("support") || normalized.includes("confirm")) return "is-success";
  if (normalized.includes("contra") || normalized.includes("refut") || normalized.includes("conflict"))
    return "is-danger";
  if (normalized.includes("mixed") || normalized.includes("unclear")) return "is-warning";
  return "";
}

function loadingNotice(label: string): React.ReactNode {
  return (
    <p role="status" className="small muted">
      {label}
    </p>
  );
}

/** An item is unresolved when it carries no settled disposition. */
function isUnresolved(item: ClearanceItem): boolean {
  return (
    item.disposition === undefined ||
    item.disposition === "pending" ||
    item.disposition === "deferred"
  );
}

export function ReportDocument({
  versions,
  items,
  sources,
  sourcesComplete,
  project,
  monitoringRuns,
  monitoringPolicy,
  trustEvaluations,
  snapshot,
  loading = false,
}: ReportDocumentProps) {
  const [active, setActive] = useState<ExhibitTab>("a");
  const openItems = items.filter(isUnresolved);

  const tabs: readonly (TabItem & { value: ExhibitTab })[] = [
    { value: "a", label: "A · Versions", count: versions.length },
    { value: "b", label: "B · Flags", count: items.length },
    { value: "c", label: "C · Sources", count: sources.length },
    { value: "d", label: "D · Project" },
    { value: "e", label: "E · Trust", count: trustEvaluations.length },
    { value: "open", label: "Open items", count: openItems.length },
    { value: "binding", label: "Binding" },
  ];

  return (
    <section
      className="section"
      data-testid="report-document"
      aria-labelledby="report-document-heading"
    >
      <div className="section-head">
        <div>
          <h2 id="report-document-heading">Clearance report document</h2>
          <p>
            A live, version-bound record of what was checked, decided, and left open. It renders
            only data returned by the clearance service.
          </p>
        </div>
      </div>

      <TabsBar
        items={tabs}
        active={active}
        onChange={(value) => setActive(value as ExhibitTab)}
        label="Report exhibits"
      />

      <div className="stack gap-t-5">
        {active === "a" && <ExhibitVersions versions={versions} loading={loading} />}
        {active === "b" && <ExhibitFlags items={items} loading={loading} />}
        {active === "c" && (
          <ExhibitSources sources={sources} complete={sourcesComplete} loading={loading} />
        )}
        {active === "d" && <ExhibitProject project={project} loading={loading} />}
        {active === "e" && (
          <ExhibitTrust
            runs={monitoringRuns}
            policy={monitoringPolicy}
            evaluations={trustEvaluations}
            loading={loading}
          />
        )}
        {active === "open" && <OpenItemsAppendix items={openItems} loading={loading} />}
        {active === "binding" && (
          <VersionBinding snapshot={snapshot} versions={versions} loading={loading} />
        )}

        <p className="small muted" role="note" data-testid="report-legal-disclaimer">
          {LEGAL_DISCLAIMER}
        </p>
      </div>
    </section>
  );
}

/* ── Exhibit A — Script versions & revision stock ───────────────────────── */

function ExhibitVersions({
  versions,
  loading,
}: {
  versions: readonly ScriptVersion[];
  loading: boolean;
}) {
  return (
    <Section
      title="Exhibit A · Script versions"
      description="Committed script versions with their revision stock and source snapshot identifiers."
    >
      {versions.length === 0 ? (
        loading ? (
          loadingNotice("Loading script versions…")
        ) : (
          <EmptyState
            icon="◦"
            title="No script versions available"
            description="No committed script version was returned for this project."
          />
        )
      ) : (
        <DataTable
          caption="Committed script versions for this project"
          columns={[
            { label: "Version" },
            { label: "Revision stock" },
            { label: "Title" },
            { label: "Scenes", align: "right" },
            { label: "Source hash" },
            { label: "Committed" },
          ]}
          rows={versions.map((version) => [
            <span key={`${version.versionId}-n`}>#{version.versionNumber}</span>,
            textOrDash(version.revisionLabel),
            textOrDash(version.title),
            version.sceneCount,
            <span className="mono small" key={`${version.versionId}-h`}>
              {textOrDash(version.sourceHash)}
            </span>,
            formatDateTime(version.createdAt),
          ])}
        />
      )}
    </Section>
  );
}

/* ── Exhibit B — Flags register ─────────────────────────────────────────── */

function ExhibitFlags({ items, loading }: { items: readonly ClearanceItem[]; loading: boolean }) {
  return (
    <Section
      title="Exhibit B · Flags register"
      description="Every detected clearance item across the ten protected categories."
    >
      {items.length === 0 ? (
        loading ? (
          loadingNotice("Loading flags…")
        ) : (
          <EmptyState
            icon="◦"
            title="No clearance items available"
            description="No clearance item was returned for this project."
          />
        )
      ) : (
        <DataTable
          caption="All clearance items with category, severity, confidence, status, and scene"
          columns={[
            { label: "Entity" },
            { label: "Category" },
            { label: "Severity" },
            { label: "Confidence" },
            { label: "Scene" },
            { label: "Status", align: "right" },
          ]}
          rows={items.map((item) => [
            textOrDash(item.entityName),
            humanizeCategory(item.category),
            textOrDash(item.severity),
            item.confidence === undefined ? (
              <span className="muted" key={`${item.itemId}-c`}>
                —
              </span>
            ) : (
              `${Math.round(item.confidence * 100)}%`
            ),
            textOrDash(item.scene),
            <Badge key={`${item.itemId}-s`} tone={statusTone(item.status)}>
              {humanizeStatus(item.displayStatus ?? item.status)}
            </Badge>,
          ])}
        />
      )}
    </Section>
  );
}

/* ── Exhibit C — Sources & authority ────────────────────────────────────── */

function ExhibitSources({
  sources,
  complete,
  loading,
}: {
  sources: readonly ReportSourceRow[];
  complete: boolean;
  loading: boolean;
}) {
  return (
    <Section
      title="Exhibit C · Sources & authority"
      description="Every retrieved source across all items with its authority tier, publisher, retrieval time, excerpt, and stance."
    >
      {!complete && !loading && sources.length > 0 && (
        <p className="small muted gap-b-4" role="note">
          Some items&apos; evidence could not be retrieved; the sources below are those that were
          returned.
        </p>
      )}
      {sources.length === 0 ? (
        loading ? (
          loadingNotice("Aggregating cited sources across items…")
        ) : (
          <EmptyState
            icon="◉"
            title="No cited sources available"
            description={
              complete
                ? "No cited source snapshot was returned for any clearance item. Zero evidence is unresolved, not clearance."
                : "Evidence could not be retrieved for this project's items. No source has been invented in its place."
            }
          />
        )
      ) : (
        <DataTable
          caption="Complete evidence provenance across all clearance items"
          columns={[
            { label: "Authority" },
            { label: "Source" },
            { label: "Cited for" },
            { label: "Retrieved" },
            { label: "Excerpt" },
            { label: "Stance", align: "right" },
          ]}
          rows={sources.map((source) => [
            <span className="mono small" key={`${source.key}-tier`}>
              {textOrDash(source.authorityTier)}
            </span>,
            source.url ? (
              <a href={source.url} target="_blank" rel="noopener noreferrer" key={`${source.key}-u`}>
                {source.publisher || source.url} ↗
              </a>
            ) : (
              textOrDash(source.publisher)
            ),
            textOrDash(source.entityName),
            formatDateTime(source.retrievedAt),
            <span className="small" key={`${source.key}-e`}>
              {source.excerpt ? `“${source.excerpt}”` : <span className="muted">—</span>}
            </span>,
            <Badge key={`${source.key}-s`} tone={stanceTone(source.stance)}>
              {textOrDash(source.stance)}
            </Badge>,
          ])}
        />
      )}
    </Section>
  );
}

/* ── Exhibit D — Project details ────────────────────────────────────────── */

function ExhibitProject({ project, loading }: { project: Project | null; loading: boolean }) {
  return (
    <Section
      title="Exhibit D · Project details"
      description="The project this report is bound to."
    >
      {project === null ? (
        loading ? (
          loadingNotice("Loading project details…")
        ) : (
          <EmptyState
            icon="◦"
            title="Project details not available"
            description="Project details were not returned by the clearance service."
          />
        )
      ) : (
        <Card>
          <dl className="report-meta">
            <div>
              <dt>Title</dt>
              <dd>{textOrDash(project.title)}</dd>
            </div>
            <div>
              <dt>Description</dt>
              <dd>{textOrDash(project.description)}</dd>
            </div>
            <div>
              <dt>Production type</dt>
              <dd>{textOrDash(project.productionType)}</dd>
            </div>
            <div>
              <dt>Production stage</dt>
              <dd>{textOrDash(project.productionStage)}</dd>
            </div>
            <div>
              <dt>Jurisdiction</dt>
              <dd>{textOrDash(project.jurisdiction)}</dd>
            </div>
            <div>
              <dt>Target lock date</dt>
              <dd>{project.targetLockDate ? formatDate(project.targetLockDate) : textOrDash(null)}</dd>
            </div>
            <div>
              <dt>Review brief</dt>
              <dd>{textOrDash(project.reviewBrief)}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatDateTime(project.createdAt)}</dd>
            </div>
          </dl>
        </Card>
      )}
    </Section>
  );
}

/* ── Exhibit E — Source watch & AI trust ────────────────────────────────── */

function ExhibitTrust({
  runs,
  policy,
  evaluations,
  loading,
}: {
  runs: readonly MonitoringRun[];
  policy: MonitoringPolicy | null;
  evaluations: readonly TrustEvaluation[];
  loading: boolean;
}) {
  return (
    <Section
      title="Exhibit E · Source watch & AI trust"
      description="Monitoring cadence and run history, plus the AI-trust posture at load time."
    >
      <div className="stack gap-lg">
        <Card title="Monitoring cadence" eyebrow="Source watch">
          {policy === null ? (
            loading ? (
              loadingNotice("Loading monitoring policy…")
            ) : (
              <p className="small muted">Monitoring policy not available.</p>
            )
          ) : (
            <dl className="report-meta">
              <div>
                <dt>Cadence</dt>
                <dd>{textOrDash(policy.cadence)}</dd>
              </div>
              <div>
                <dt>Active</dt>
                <dd>{policy.active ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt>Last run</dt>
                <dd>{policy.lastRunAt ? formatDateTime(policy.lastRunAt) : textOrDash(null)}</dd>
              </div>
            </dl>
          )}
        </Card>

        <div>
          <h3 className="small">Monitoring runs ({runs.length})</h3>
          {runs.length === 0 ? (
            loading ? (
              loadingNotice("Loading monitoring runs…")
            ) : (
              <EmptyState
                icon="◉"
                title="No monitoring runs recorded"
                description="No monitoring run has persisted results for this project."
              />
            )
          ) : (
            <DataTable
              caption="Monitoring run history"
              columns={[
                { label: "Status" },
                { label: "Items checked", align: "right" },
                { label: "Changes detected", align: "right" },
                { label: "Run at" },
              ]}
              rows={runs.map((run) => [
                <Badge
                  key={`${run.runId}-s`}
                  tone={run.status === "failed" ? "is-danger" : "is-success"}
                >
                  {humanizeStatus(run.status)}
                </Badge>,
                run.itemsChecked,
                run.changesDetected,
                formatDateTime(run.createdAt),
              ])}
            />
          )}
        </div>

        <div>
          <h3 className="small">AI-trust evaluations ({evaluations.length})</h3>
          {evaluations.length === 0 ? (
            loading ? (
              loadingNotice("Loading AI-trust evaluations…")
            ) : (
              <EmptyState
                icon="◦"
                title="No AI-trust evaluations available"
                description="No trust evaluation was returned for this project."
              />
            )
          ) : (
            <DataTable
              caption="AI-trust evaluation posture across grading stages"
              columns={[
                { label: "Stage" },
                { label: "Headline score", align: "right" },
                { label: "Blockers", align: "right" },
                { label: "Graded by model" },
                { label: "Rubric" },
                { label: "Evaluated" },
              ]}
              rows={evaluations.map((evaluation) => [
                humanizeStatus(evaluation.stage),
                evaluation.headlineScore === null ? (
                  <span className="muted" key={`${evaluation.evaluationId}-h`}>
                    Not scored
                  </span>
                ) : (
                  <span className="mono" key={`${evaluation.evaluationId}-h`}>
                    {evaluation.headlineScore}
                  </span>
                ),
                <Badge
                  key={`${evaluation.evaluationId}-b`}
                  tone={evaluation.blockersCount > 0 ? "is-danger" : "is-success"}
                >
                  {evaluation.blockersCount}
                </Badge>,
                textOrDash(evaluation.provenance.returnedModel ?? evaluation.provenance.requestedModel),
                <span className="mono small" key={`${evaluation.evaluationId}-r`}>
                  {textOrDash(evaluation.provenance.rubricVersion)}
                </span>,
                formatDateTime(evaluation.createdAt),
              ])}
            />
          )}
        </div>
      </div>
    </Section>
  );
}

/* ── Open items appendix ────────────────────────────────────────────────── */

function OpenItemsAppendix({
  items,
  loading,
}: {
  items: readonly ClearanceItem[];
  loading: boolean;
}) {
  return (
    <Section
      title="Open items"
      description="Items without a final disposition — carried, not hidden."
    >
      {items.length === 0 ? (
        loading ? (
          loadingNotice("Loading open items…")
        ) : (
          <EmptyState
            icon="✓"
            title="No open items"
            description="Every clearance item carries a settled disposition."
          />
        )
      ) : (
        <DataTable
          caption="Clearance items still awaiting a final disposition"
          columns={[
            { label: "Entity" },
            { label: "Category" },
            { label: "Disposition" },
            { label: "Scene" },
            { label: "Status", align: "right" },
          ]}
          rows={items.map((item) => [
            textOrDash(item.entityName),
            humanizeCategory(item.category),
            textOrDash(item.disposition ?? "pending"),
            textOrDash(item.scene),
            <Badge key={`${item.itemId}-s`} tone={statusTone(item.status)}>
              {humanizeStatus(item.displayStatus ?? item.status)}
            </Badge>,
          ])}
        />
      )}
    </Section>
  );
}

/* ── Version binding ────────────────────────────────────────────────────── */

/**
 * The reproducibility proof. When a snapshot exists, the frozen `contentHash`
 * and any known keys read defensively from the untyped `bindingManifest` are
 * shown as the authoritative binding. Absent a snapshot, the live draft binding
 * is assembled from the committed versions only — nothing is fabricated.
 */
function VersionBinding({
  snapshot,
  versions,
  loading,
}: {
  snapshot: ReportSnapshot | null;
  versions: readonly ScriptVersion[];
  loading: boolean;
}) {
  const manifest = snapshot?.bindingManifest ?? null;

  const manifestValue = (key: string): string | null => {
    if (!manifest) return null;
    const value = manifest[key];
    if (value === null || value === undefined) return null;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    return JSON.stringify(value);
  };

  // Known manifest keys are read defensively; missing keys render as "not available".
  const bindingRows: Array<[string, React.ReactNode]> = [
    [
      "Report status",
      snapshot ? (
        <Badge tone={snapshot.status === "released" ? "is-success" : "is-warning"}>
          {humanizeStatus(snapshot.status)}
        </Badge>
      ) : (
        <span className="muted">Draft (no snapshot generated)</span>
      ),
    ],
    [
      "Bound script version",
      snapshot ? (
        <span className="mono small">{textOrDash(snapshot.versionId)}</span>
      ) : versions[0] ? (
        <span className="mono small">
          #{versions[0].versionNumber} · {textOrDash(versions[0].sourceHash)}
        </span>
      ) : (
        <span className="muted">{NOT_AVAILABLE}</span>
      ),
    ],
    ["Sign-off / policy version", manifestValueOrDash(manifestValue("policyVersion"))],
    ["Prompt version", manifestValueOrDash(manifestValue("promptVersion"))],
    ["Grading rubric version", manifestValueOrDash(manifestValue("rubricVersion"))],
    ["Graded-by model", manifestValueOrDash(manifestValue("judgeModel") ?? manifestValue("returnedModel"))],
    ["Grade", manifestValueOrDash(manifestValue("headlineScore") ?? manifestValue("grade"))],
    [
      "Snapshot content hash",
      snapshot ? (
        <span className="mono small">{textOrDash(snapshot.contentHash)}</span>
      ) : (
        <span className="muted">Computed at generation</span>
      ),
    ],
    [
      "Generated at",
      snapshot ? formatDateTime(snapshot.generatedAt) : <span className="muted">{NOT_AVAILABLE}</span>,
    ],
  ];

  return (
    <Section
      title="Binding"
      description="The exact input versions this report is bound to — the reproducibility proof."
    >
      {loading && !snapshot && versions.length === 0 ? (
        loadingNotice("Loading binding manifest…")
      ) : (
        <>
          {!snapshot && (
            <p className="small muted gap-b-4" role="note">
              No frozen snapshot has been generated yet. The binding below is a live draft assembled
              from the committed script version; frozen policy, prompt, rubric, judge, and hash
              values become available once a snapshot is generated.
            </p>
          )}
          <Card>
            <dl className="report-meta" data-testid="report-binding-manifest">
              {bindingRows.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </>
      )}
    </Section>
  );
}

function manifestValueOrDash(value: string | null): React.ReactNode {
  if (value === null) {
    return <span className="muted">{NOT_AVAILABLE}</span>;
  }
  return <span className="mono small">{value}</span>;
}

export default ReportDocument;
