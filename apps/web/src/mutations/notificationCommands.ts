import type { QueryClient } from "@tanstack/react-query";
import {
  api,
  type ApiError,
  type NotificationDeliveryPreference,
} from "@clearcut/contracts";
import { notificationKeys } from "../queries/notifications";

type SetPreferenceClient = Pick<typeof api, "setNotificationDeliveryPreference">;

/** The channels the contract accepts for a personal delivery preference. */
export type DeliveryChannel = NotificationDeliveryPreference["channel"];

function toCommandError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function executeSetNotificationDeliveryPreference(
  orgId: string,
  channel: DeliveryChannel,
  client: SetPreferenceClient = api,
): Promise<NotificationDeliveryPreference> {
  const result = await client.setNotificationDeliveryPreference({
    params: { orgId },
    body: { channel },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

/**
 * Setting the caller's own delivery channel.
 *
 * This is a personal preference, not a governed action: any active member may
 * set their own channel, so there is no capability gate and no idempotency key
 * declared in the contract. On success we seed the cached preference with the
 * authoritative server response so the control reflects what is actually
 * stored rather than what was optimistically selected.
 */
export function setNotificationDeliveryPreferenceMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: SetPreferenceClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (channel: DeliveryChannel) =>
      executeSetNotificationDeliveryPreference(orgId, channel, client),
    onSuccess: (preference: NotificationDeliveryPreference) => {
      queryClient.setQueryData(
        notificationKeys.deliveryPreference(orgId),
        preference,
      );
    },
  };
}
