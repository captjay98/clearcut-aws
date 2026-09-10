import { queryOptions } from "@tanstack/react-query";
import type { NotificationDeliveryPreference } from "@clearcut/contracts";

export const notificationKeys = {
  deliveryPreference: (orgId: string) =>
    ["notification-delivery-preference", orgId] as const,
};

/**
 * The channel the caller receives notifications on.
 *
 * The contract exposes a setter (`setNotificationDeliveryPreference`) but no
 * reader for the current value, so this "query" never hits the network: it
 * seeds a sensible default of in-app delivery and then reflects whatever the
 * setter last stored via `setQueryData`. Defaulting to `in_app` is the
 * conservative choice — it keeps notifications inside the workspace and does
 * not assume the caller has opted into email or push until they say so.
 *
 * Modelling it as a query rather than local component state means the selected
 * channel survives navigation away from Settings and is shared by any other
 * surface that wants to display it, and the mutation's cache write is the one
 * source of truth for the value.
 */
export const DEFAULT_DELIVERY_CHANNEL: NotificationDeliveryPreference["channel"] =
  "in_app";

export function notificationDeliveryPreferenceQueryOptions(orgId: string) {
  return queryOptions({
    queryKey: notificationKeys.deliveryPreference(orgId),
    // No read endpoint exists: resolve immediately with the default. Once the
    // caller sets a channel, the mutation seeds this same cache entry, so the
    // control shows the stored value without ever needing to refetch.
    queryFn: async (): Promise<NotificationDeliveryPreference> => ({
      channel: DEFAULT_DELIVERY_CHANNEL,
    }),
    staleTime: Infinity,
  });
}
