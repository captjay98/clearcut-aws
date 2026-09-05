import type { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import {
  acknowledgeReferralMutationOptions,
  addCommentMutationOptions,
  assignClearanceItemMutationOptions,
  executeAcknowledgeReferral,
  executeAddComment,
  executeAssignClearanceItem,
  executeRecordEvidenceDecision,
  executeReferClearanceItem,
  executeReplyToComment,
  executeReviseComment,
  executeSetDisposition,
  recordEvidenceDecisionMutationOptions,
  referClearanceItemMutationOptions,
  replyToCommentMutationOptions,
  reviseCommentMutationOptions,
  setDispositionMutationOptions,
} from "../../src/mutations/clearanceItemCommands";
import {
  clearanceItemDetailQueryOptions,
  clearanceItemKeys,
  clearanceItemsQueryOptions,
  loadClearanceItem,
  loadClearanceItems,
} from "../../src/queries/clearanceItems";

describe("Task 10 authoritative item state", () => {
  it("preserves exact item identity in detail query keys", () => {
    expect(clearanceItemKeys.detail("org-1", "project-1", "item-1")).toEqual([
      "clearance-items",
      "org-1",
      "project-1",
      "detail",
      "item-1",
    ]);
    expect(clearanceItemKeys.detail("org-1", "project-1", "item-2")).not.toEqual(
      clearanceItemKeys.detail("org-1", "project-1", "item-1"),
    );
  });

  it("surfaces typed generated-client failures to TanStack Query", async () => {
    const error = {
      code: "permission_denied" as const,
      message: "Project access is required.",
      requestId: "request-1",
      retryable: false,
    };
    const client = {
      getClearanceItem: vi.fn(async () => ({ ok: false as const, error })),
    };

    await expect(
      loadClearanceItem(
        { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
        client,
      ),
    ).rejects.toMatchObject(error);
  });

  it("executes the canonical evidence-decision command with concurrency identity", async () => {
    const value = {
      itemId: "item-1",
      projectId: "project-1",
      version: 4,
      category: "products_and_trademarks",
      entityName: "Vega Camera",
      status: "unresolved",
    };
    const client = {
      recordEvidenceDecision: vi.fn(async () => ({ ok: true as const, value })),
    };

    await expect(
      executeRecordEvidenceDecision(
        { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
        {
          decision: "accepted",
          rationale: "Reviewed cited primary-source material.",
          expectedVersion: 3,
          intentHash: "a".repeat(64),
          idempotencyKey: "decision-command-0001",
        },
        client,
      ),
    ).resolves.toEqual(value);
    expect(client.recordEvidenceDecision).toHaveBeenCalledOnce();
    expect(client.recordEvidenceDecision).toHaveBeenCalledWith({
      params: { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
      headers: { "Idempotency-Key": "decision-command-0001" },
      body: {
        decision: "accepted",
        rationale: "Reviewed cited primary-source material.",
        expectedVersion: 3,
        intentHash: "a".repeat(64),
      },
    });
  });

  it("disables retries and refetches exact authoritative state after success", async () => {
    const invalidateQueries = vi.fn(async () => undefined);
    const queryClient = { invalidateQueries } as unknown as QueryClient;
    const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };
    const client = {
      recordEvidenceDecision: vi.fn(),
    };

    const options = recordEvidenceDecisionMutationOptions(scope, queryClient, client);

    expect(options.retry).toBe(false);
    expect("onMutate" in options).toBe(false);
    await options.onSuccess();
    expect(invalidateQueries.mock.calls).toEqual([
      [{ queryKey: clearanceItemKeys.list("org-1", "project-1") }],
      [
        {
          queryKey: clearanceItemKeys.detail("org-1", "project-1", "item-1"),
          exact: true,
        },
      ],
      [
        {
          queryKey: clearanceItemKeys.evidence("org-1", "project-1", "item-1"),
          exact: true,
        },
      ],
      [{ queryKey: ["records", "org-1"] }],
    ]);
  });
});



it("loads only the requested project's authoritative item list", async () => {
  const value = [
    {
      itemId: "item-1",
      projectId: "project-1",
      version: 1,
      category: "products_and_trademarks",
      entityName: "Vega Camera",
      status: "unresolved",
    },
  ];
  const client = {
    listClearanceItems: vi.fn(async () => ({ ok: true as const, value })),
  };

  await expect(
    loadClearanceItems({ orgId: "org-1", projectId: "project-1" }, client),
  ).resolves.toEqual(value);
  expect(client.listClearanceItems).toHaveBeenCalledWith({
    params: { orgId: "org-1", projectId: "project-1" },
  });
});



it("builds shared list and exact-detail query options", () => {
  const client = {
    listClearanceItems: vi.fn(),
    getClearanceItem: vi.fn(),
  };

  const list = clearanceItemsQueryOptions(
    { orgId: "org-1", projectId: "project-1" },
    client,
  );
  const detail = clearanceItemDetailQueryOptions(
    { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
    client,
  );

  expect(list.queryKey).toEqual(clearanceItemKeys.list("org-1", "project-1"));
  expect(detail.queryKey).toEqual(
    clearanceItemKeys.detail("org-1", "project-1", "item-1"),
  );
});



it("executes add-comment through the canonical generated operation", async () => {
  const value = {
    commentId: "comment-1",
    itemId: "item-1",
    itemVersion: 5,
    authorId: "actor-1",
    body: "Please verify the registry date.",
    createdAt: "2026-09-06T00:00:00Z",
  };
  const client = {
    addComment: vi.fn(async () => ({ ok: true as const, value })),
  };

  await expect(
    executeAddComment(
      { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
      {
        body: "Please verify the registry date.",
        mentions: ["01900000-0000-7000-8000-000000000001"],
        expectedVersion: 4,
        intentHash: "b".repeat(64),
        idempotencyKey: "comment-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.addComment).toHaveBeenCalledWith({
    params: { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
    headers: { "Idempotency-Key": "comment-command-0001" },
    body: {
      body: "Please verify the registry date.",
      mentions: ["01900000-0000-7000-8000-000000000001"],
      expectedVersion: 4,
      intentHash: "b".repeat(64),
    },
  });
});



it("keeps comment writes non-optimistic and refreshes persisted history", async () => {
  const invalidateQueries = vi.fn(async () => undefined);
  const queryClient = { invalidateQueries } as unknown as QueryClient;
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };
  const client = { addComment: vi.fn() };

  const options = addCommentMutationOptions(scope, queryClient, client);

  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
  await options.onSuccess();
  expect(invalidateQueries).toHaveBeenCalledWith({
    queryKey: clearanceItemKeys.detail("org-1", "project-1", "item-1"),
    exact: true,
  });
});



it("executes referral submission through the canonical generated operation", async () => {
  const value = {
    referralId: "referral-1",
    itemId: "item-1",
    itemVersion: 6,
    targetRole: "reviewer",
    question: "Does the cited registry record resolve the identity conflict?",
    status: "submitted",
  };
  const client = {
    referClearanceItem: vi.fn(async () => ({ ok: true as const, value })),
  };

  await expect(
    executeReferClearanceItem(
      { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
      {
        targetRole: "reviewer",
        question: "Does the cited registry record resolve the identity conflict?",
        rationale: "A specialist must assess the conflicting record.",
        expectedVersion: 5,
        intentHash: "c".repeat(64),
        idempotencyKey: "referral-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.referClearanceItem).toHaveBeenCalledWith({
    params: { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
    headers: { "Idempotency-Key": "referral-command-0001" },
    body: {
      targetRole: "reviewer",
      question: "Does the cited registry record resolve the identity conflict?",
      rationale: "A specialist must assess the conflicting record.",
      expectedVersion: 5,
      intentHash: "c".repeat(64),
    },
  });
});



it("keeps referral submission non-optimistic and refreshes persisted lifecycle", async () => {
  const invalidateQueries = vi.fn(async () => undefined);
  const queryClient = { invalidateQueries } as unknown as QueryClient;
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };
  const options = referClearanceItemMutationOptions(scope, queryClient, {
    referClearanceItem: vi.fn(),
  });

  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
  await options.onSuccess();
  expect(invalidateQueries).toHaveBeenCalledWith({
    queryKey: clearanceItemKeys.detail("org-1", "project-1", "item-1"),
    exact: true,
  });
});



it("acknowledges a persisted referral through the canonical generated operation", async () => {
  const value = {
    referralId: "referral-1",
    itemId: "item-1",
    itemVersion: 7,
    targetRole: "reviewer",
    question: "Does the cited record resolve the conflict?",
    response: "The conflict remains unresolved.",
    status: "acknowledged",
  };
  const client = {
    acknowledgeReferral: vi.fn(async () => ({ ok: true as const, value })),
  };
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };

  await expect(
    executeAcknowledgeReferral(
      scope,
      {
        referralId: "referral-1",
        response: "The conflict remains unresolved.",
        rationale: "The cited source identifies a different entity.",
        expectedVersion: 6,
        intentHash: "d".repeat(64),
        idempotencyKey: "acknowledgement-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.acknowledgeReferral).toHaveBeenCalledWith({
    params: {
      orgId: "org-1",
      projectId: "project-1",
      itemId: "item-1",
      referralId: "referral-1",
    },
    headers: { "Idempotency-Key": "acknowledgement-command-0001" },
    body: {
      response: "The conflict remains unresolved.",
      rationale: "The cited source identifies a different entity.",
      expectedVersion: 6,
      intentHash: "d".repeat(64),
    },
  });

  const invalidateQueries = vi.fn(async () => undefined);
  const options = acknowledgeReferralMutationOptions(
    scope,
    { invalidateQueries } as unknown as QueryClient,
    client,
  );
  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
  await options.onSuccess();
  expect(invalidateQueries).toHaveBeenCalledWith({
    queryKey: clearanceItemKeys.detail("org-1", "project-1", "item-1"),
    exact: true,
  });
});



it("records a reply through the canonical generated operation", async () => {
  const value = {
    commentId: "reply-1",
    itemId: "item-1",
    itemVersion: 8,
    authorId: "actor-2",
    body: "The cited date still needs review.",
    parentId: "comment-1",
    createdAt: "2026-09-06T01:00:00Z",
  };
  const client = {
    replyToComment: vi.fn(async () => ({ ok: true as const, value })),
  };
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };

  await expect(
    executeReplyToComment(
      scope,
      {
        commentId: "comment-1",
        body: "The cited date still needs review.",
        mentions: ["01900000-0000-7000-8000-000000000002"],
        expectedVersion: 7,
        intentHash: "e".repeat(64),
        idempotencyKey: "reply-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.replyToComment).toHaveBeenCalledWith({
    params: {
      orgId: "org-1",
      projectId: "project-1",
      itemId: "item-1",
      commentId: "comment-1",
    },
    headers: { "Idempotency-Key": "reply-command-0001" },
    body: {
      body: "The cited date still needs review.",
      mentions: ["01900000-0000-7000-8000-000000000002"],
      expectedVersion: 7,
      intentHash: "e".repeat(64),
    },
  });

  const options = replyToCommentMutationOptions(
    scope,
    { invalidateQueries: vi.fn(async () => undefined) } as unknown as QueryClient,
    client,
  );
  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
});



it("records a comment revision through the canonical generated operation", async () => {
  const value = {
    commentId: "comment-1",
    itemId: "item-1",
    itemVersion: 9,
    authorId: "actor-1",
    body: "Corrected source retrieval date.",
    createdAt: "2026-09-06T02:00:00Z",
  };
  const client = {
    reviseComment: vi.fn(async () => ({ ok: true as const, value })),
  };
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };

  await expect(
    executeReviseComment(
      scope,
      {
        commentId: "comment-1",
        body: "Corrected source retrieval date.",
        mentions: [],
        expectedVersion: 8,
        intentHash: "f".repeat(64),
        idempotencyKey: "revision-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.reviseComment).toHaveBeenCalledWith({
    params: {
      orgId: "org-1",
      projectId: "project-1",
      itemId: "item-1",
      commentId: "comment-1",
    },
    headers: { "Idempotency-Key": "revision-command-0001" },
    body: {
      body: "Corrected source retrieval date.",
      mentions: [],
      expectedVersion: 8,
      intentHash: "f".repeat(64),
    },
  });

  const options = reviseCommentMutationOptions(
    scope,
    { invalidateQueries: vi.fn(async () => undefined) } as unknown as QueryClient,
    client,
  );
  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
});



it("assigns an item through the canonical generated operation", async () => {
  const value = {
    itemId: "item-1",
    projectId: "project-1",
    version: 10,
    category: "products_and_trademarks",
    entityName: "Vega Camera",
    status: "unresolved",
    assignedTo: "member-2",
  };
  const client = {
    assignClearanceItem: vi.fn(async () => ({ ok: true as const, value })),
  };
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };

  await expect(
    executeAssignClearanceItem(
      scope,
      {
        assigneeId: "member-2",
        expectedVersion: 9,
        intentHash: "1".repeat(64),
        idempotencyKey: "assignment-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.assignClearanceItem).toHaveBeenCalledWith({
    params: { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
    headers: { "Idempotency-Key": "assignment-command-0001" },
    body: {
      assigneeId: "member-2",
      expectedVersion: 9,
      intentHash: "1".repeat(64),
    },
  });

  const options = assignClearanceItemMutationOptions(
    scope,
    { invalidateQueries: vi.fn(async () => undefined) } as unknown as QueryClient,
    client,
  );
  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
});



it("sets disposition through the canonical generated operation", async () => {
  const value = {
    itemId: "item-1",
    projectId: "project-1",
    version: 11,
    category: "products_and_trademarks",
    entityName: "Vega Camera",
    status: "unresolved",
    disposition: "deferred" as const,
  };
  const client = {
    setDisposition: vi.fn(async () => ({ ok: true as const, value })),
  };
  const scope = { orgId: "org-1", projectId: "project-1", itemId: "item-1" };

  await expect(
    executeSetDisposition(
      scope,
      {
        disposition: "deferred",
        rationale: "Qualified review is still required.",
        expectedVersion: 10,
        intentHash: "2".repeat(64),
        idempotencyKey: "disposition-command-0001",
      },
      client,
    ),
  ).resolves.toEqual(value);
  expect(client.setDisposition).toHaveBeenCalledWith({
    params: { orgId: "org-1", projectId: "project-1", itemId: "item-1" },
    headers: { "Idempotency-Key": "disposition-command-0001" },
    body: {
      disposition: "deferred",
      rationale: "Qualified review is still required.",
      expectedVersion: 10,
      intentHash: "2".repeat(64),
    },
  });

  const options = setDispositionMutationOptions(
    scope,
    { invalidateQueries: vi.fn(async () => undefined) } as unknown as QueryClient,
    client,
  );
  expect(options.retry).toBe(false);
  expect("onMutate" in options).toBe(false);
});
