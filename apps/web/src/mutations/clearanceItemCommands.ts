import type { QueryClient } from "@tanstack/react-query";
import {
  api,
  type AcknowledgeReferralRequest,
  type AddCommentRequest,
  type AssignClearanceItemRequest,
  type ApiError,
  type ClearanceItem,
  type Comment as CommentResult,
  type RecordEvidenceDecisionRequest,
  type Referral,
  type ReferClearanceItemRequest,
  type ReplyToCommentRequest,
  type ReviseCommentRequest,
  type SetDispositionRequest,
} from "@clearcut/contracts";
import {
  clearanceItemKeys,
  type ClearanceItemScope,
} from "../queries/clearanceItems";

type EvidenceDecisionClient = Pick<typeof api, "recordEvidenceDecision">;
type AssignmentClient = Pick<typeof api, "assignClearanceItem">;
type DispositionClient = Pick<typeof api, "setDisposition">;
type AddCommentClient = Pick<typeof api, "addComment">;
type ReferralClient = Pick<typeof api, "referClearanceItem">;
type AcknowledgeReferralClient = Pick<typeof api, "acknowledgeReferral">;
type ReplyToCommentClient = Pick<typeof api, "replyToComment">;
type ReviseCommentClient = Pick<typeof api, "reviseComment">;

export interface RecordEvidenceDecisionInput extends RecordEvidenceDecisionRequest {
  idempotencyKey: string;
}

export interface AssignClearanceItemInput extends AssignClearanceItemRequest {
  idempotencyKey: string;
}

export interface SetDispositionInput extends SetDispositionRequest {
  idempotencyKey: string;
}

export interface AddCommentInput extends AddCommentRequest {
  idempotencyKey: string;
}

export interface ReferClearanceItemInput extends ReferClearanceItemRequest {
  idempotencyKey: string;
}

export interface AcknowledgeReferralInput extends AcknowledgeReferralRequest {
  referralId: string;
  idempotencyKey: string;
}

export interface ReplyToCommentInput extends ReplyToCommentRequest {
  commentId: string;
  idempotencyKey: string;
}

export interface ReviseCommentInput extends ReviseCommentRequest {
  commentId: string;
  idempotencyKey: string;
}

function toCommandError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function executeAssignClearanceItem(
  scope: ClearanceItemScope,
  input: AssignClearanceItemInput,
  client: AssignmentClient = api,
): Promise<ClearanceItem> {
  const result = await client.assignClearanceItem({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      ...(input.assigneeId !== undefined ? { assigneeId: input.assigneeId } : {}),
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeSetDisposition(
  scope: ClearanceItemScope,
  input: SetDispositionInput,
  client: DispositionClient = api,
): Promise<ClearanceItem> {
  const result = await client.setDisposition({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      disposition: input.disposition,
      rationale: input.rationale,
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeRecordEvidenceDecision(
  scope: ClearanceItemScope,
  input: RecordEvidenceDecisionInput,
  client: EvidenceDecisionClient = api,
): Promise<ClearanceItem> {
  const result = await client.recordEvidenceDecision({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      decision: input.decision,
      rationale: input.rationale,
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}



export async function executeAddComment(
  scope: ClearanceItemScope,
  input: AddCommentInput,
  client: AddCommentClient = api,
): Promise<CommentResult> {
  const result = await client.addComment({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      body: input.body,
      ...(input.mentions ? { mentions: input.mentions } : {}),
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeReferClearanceItem(
  scope: ClearanceItemScope,
  input: ReferClearanceItemInput,
  client: ReferralClient = api,
): Promise<Referral> {
  const result = await client.referClearanceItem({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      targetRole: input.targetRole,
      question: input.question,
      rationale: input.rationale,
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeAcknowledgeReferral(
  scope: ClearanceItemScope,
  input: AcknowledgeReferralInput,
  client: AcknowledgeReferralClient = api,
): Promise<Referral> {
  const result = await client.acknowledgeReferral({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
      referralId: input.referralId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      response: input.response,
      rationale: input.rationale,
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeReplyToComment(
  scope: ClearanceItemScope,
  input: ReplyToCommentInput,
  client: ReplyToCommentClient = api,
): Promise<CommentResult> {
  const result = await client.replyToComment({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
      commentId: input.commentId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      body: input.body,
      ...(input.mentions ? { mentions: input.mentions } : {}),
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeReviseComment(
  scope: ClearanceItemScope,
  input: ReviseCommentInput,
  client: ReviseCommentClient = api,
): Promise<CommentResult> {
  const result = await client.reviseComment({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
      commentId: input.commentId,
    },
    headers: { "Idempotency-Key": input.idempotencyKey },
    body: {
      body: input.body,
      ...(input.mentions ? { mentions: input.mentions } : {}),
      expectedVersion: input.expectedVersion,
      intentHash: input.intentHash,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

async function invalidateAuthoritativeItemState(
  queryClient: QueryClient,
  scope: ClearanceItemScope,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: clearanceItemKeys.list(scope.orgId, scope.projectId),
  });
  await queryClient.invalidateQueries({
    queryKey: clearanceItemKeys.detail(scope.orgId, scope.projectId, scope.itemId),
    exact: true,
  });
  await queryClient.invalidateQueries({
    queryKey: clearanceItemKeys.evidence(scope.orgId, scope.projectId, scope.itemId),
    exact: true,
  });
  await queryClient.invalidateQueries({ queryKey: ["records", scope.orgId] });
}

export function recordEvidenceDecisionMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: EvidenceDecisionClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: RecordEvidenceDecisionInput) =>
      executeRecordEvidenceDecision(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function addCommentMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: AddCommentClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: AddCommentInput) => executeAddComment(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function referClearanceItemMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: ReferralClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: ReferClearanceItemInput) =>
      executeReferClearanceItem(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function acknowledgeReferralMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: AcknowledgeReferralClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: AcknowledgeReferralInput) =>
      executeAcknowledgeReferral(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function replyToCommentMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: ReplyToCommentClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: ReplyToCommentInput) =>
      executeReplyToComment(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function reviseCommentMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: ReviseCommentClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: ReviseCommentInput) =>
      executeReviseComment(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function assignClearanceItemMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: AssignmentClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: AssignClearanceItemInput) =>
      executeAssignClearanceItem(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}



export function setDispositionMutationOptions(
  scope: ClearanceItemScope,
  queryClient: QueryClient,
  client: DispositionClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: SetDispositionInput) =>
      executeSetDisposition(scope, input, client),
    onSuccess: () => invalidateAuthoritativeItemState(queryClient, scope),
  };
}
