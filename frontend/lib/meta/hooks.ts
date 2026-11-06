"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

import type { components } from "@/types/api";

export type MetaResponse = components["schemas"]["MetaResponse"];

/**
 * Fetch the backend's public metadata via GET /meta: which AI provider
 * serves generation and the app version.
 *
 * Both only change when the backend restarts, so one answer lasts for
 * the life of the page. One retry covers a dropped request without
 * hammering an older backend, which has no /meta and answers 404.
 */
export function useMetaQuery() {
  return useQuery<MetaResponse, Error>({
    queryKey: ["meta"],
    queryFn: async () => {
      const { data, response } = await api.GET("/meta");
      // /meta declares no error response, so the types rule out
      // `error`. Any non-2xx answer still arrives without `data`.
      if (!data) {
        throw new Error(`GET /meta failed with HTTP ${response.status}.`);
      }
      return data;
    },
    staleTime: Infinity,
    retry: 1,
  });
}
