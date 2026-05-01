import { useQuery } from "@tanstack/react-query";

import { alerts } from "@/api/alerts";

export function useUnreadAlertsCount() {
  return useQuery({
    queryKey: ["alerts", "unread-count"],
    queryFn: () => alerts.unreadCount(),
    refetchInterval: 60_000, // poll every minute
  });
}
