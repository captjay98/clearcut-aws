import { queryOptions } from "@tanstack/react-query";
import {
  api,
  type ApiError,
  type ClearanceItem,
  type ClearanceItemDetail,
} from "@clearcut/contracts";

export interface ClearanceProjectScope {
  orgId: string;
  projectId: string;
}

export interface ClearanceItemScope extends ClearanceProjectScope {
  itemId: string;
}

type ItemListClient = Pick<typeof api, "listClearanceItems">;
type ItemDetailClient = Pick<typeof api, "getClearanceItem">;

export const clearanceItemKeys = {
  list: (orgId: string, projectId: string) =>
    ["clearance-items", orgId, projectId] as const,
  detail: (orgId: string, projectId: string, itemId: string) =>
    ["clearance-items", orgId, projectId, "detail", itemId] as const,
  evidence: (orgId: string, projectId: string, itemId: string) =>
    ["clearance-items", orgId, projectId, "evidence", itemId] as const,
};

export function toQueryError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function loadClearanceItems(
  scope: ClearanceProjectScope,
  client: ItemListClient = api,
): Promise<ClearanceItem[]> {
  const result = await client.listClearanceItems({
    params: { orgId: scope.orgId, projectId: scope.projectId },
  });
  if (!result.ok) throw toQueryError(result.error);
  return result.value;
}

export async function loadClearanceItem(
  scope: ClearanceItemScope,
  client: ItemDetailClient = api,
): Promise<ClearanceItemDetail> {
  const result = await client.getClearanceItem({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
  });
  if (!result.ok) throw toQueryError(result.error);
  return result.value;
}



export function clearanceItemsQueryOptions(
  scope: ClearanceProjectScope,
  client: ItemListClient = api,
) {
  return queryOptions({
    queryKey: clearanceItemKeys.list(scope.orgId, scope.projectId),
    queryFn: () => loadClearanceItems(scope, client),
  });
}

export function clearanceItemDetailQueryOptions(
  scope: ClearanceItemScope,
  client: ItemDetailClient = api,
) {
  return queryOptions({
    queryKey: clearanceItemKeys.detail(scope.orgId, scope.projectId, scope.itemId),
    queryFn: () => loadClearanceItem(scope, client),
  });
}
