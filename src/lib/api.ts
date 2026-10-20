import { supabase } from "@/integrations/supabase/custom-client";
import { API_URL } from "@/lib/constants";
import { ApiError, requestApi } from "@/lib/api-request";

export function authenticatedApi<T>(path: string, init?: RequestInit): Promise<T> {
  return requestApi<T>(path, init, {
    baseUrl: API_URL,
    accessToken: async (refresh) => {
      const { data, error } = refresh
        ? await supabase.auth.refreshSession()
        : await supabase.auth.getSession();
      if (error || !data.session)
        throw new ApiError(401, "Your session is invalid or expired. Sign in again.");
      return data.session.access_token;
    },
  });
}
