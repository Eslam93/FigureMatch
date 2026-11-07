"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { AI_ERROR_MESSAGES } from "@/lib/errors/ai-codes";

import type { GenerateInput } from "@/lib/validation/generate";
import type { components } from "@/types/api";

export type GenerateResponse = components["schemas"]["GenerateResponse"];
export type ContentType = components["schemas"]["ContentType"];
export type ContentListItem = components["schemas"]["ContentListItem"];
export type ContentListResponse = components["schemas"]["ContentListResponse"];
export type ContentDetailResponse = components["schemas"]["ContentDetailResponse"];

type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

// generateErrorMessage serves the content, image, improver and
// brand-voice hooks. The AI-provider codes come from the shared
// module; the other entries belong to these endpoints.
const FRIENDLY_MESSAGES: Record<string, string> = {
  ...AI_ERROR_MESSAGES,
  VALIDATION_FAILED: "Some fields don't look right — check the form.",
  RATE_LIMITED: "You've hit the per-minute generate limit. Wait a minute and try again.",
  MISSING_TOKEN: "Your session has expired. Sign in again.",
  TOKEN_EXPIRED: "Your session has expired. Sign in again.",
  INVALID_TOKEN: "Your session has expired. Sign in again.",
  CONTENT_NOT_FOUND: "That content doesn't exist anymore.",
  CONTENT_NOT_DELETED: "That content is already active — nothing to restore.",
  RESTORE_WINDOW_EXPIRED:
    "The 24-hour undo window has expired. Deleted content can no longer be restored.",
};

export function generateErrorMessage(
  body: unknown,
  fallback = "Something went wrong generating content. Try again.",
): string {
  const envelope = body as ErrorEnvelope | undefined;
  if (!envelope?.error) return fallback;
  return FRIENDLY_MESSAGES[envelope.error.code] ?? envelope.error.message ?? fallback;
}

/**
 * Submit a generate request. The mutation's `data` is the full
 * GenerateResponse — caller renders `result` if non-null, or shows a
 * fallback-mode banner with `rendered_text` when result_parse_status
 * is "failed".
 */
export function useGenerateMutation() {
  const queryClient = useQueryClient();
  return useMutation<GenerateResponse, Error, GenerateInput>({
    mutationFn: async (input) => {
      // Convert empty-string optionals to undefined so the backend sees
      // an absent field rather than a "" that would fail max_length=0.
      const body = {
        content_type: input.content_type,
        topic: input.topic.trim(),
        tone: input.tone?.trim() ? input.tone.trim() : undefined,
        target_audience: input.target_audience?.trim() ? input.target_audience.trim() : undefined,
        brand_voice_id: input.brand_voice_id?.trim() ? input.brand_voice_id.trim() : undefined,
      };
      const { data, error, response } = await api.POST("/content/generate", {
        body,
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      // Dashboard list should reflect the new row immediately.
      queryClient.invalidateQueries({ queryKey: ["content", "list"] });
    },
  });
}

// ── Dashboard hooks (Slice 4) ──────────────────────────────────────────

export interface ContentListFilters {
  contentType?: ContentType;
  q?: string;
  page?: number;
  pageSize?: number;
}

/**
 * List the caller's content. Filters are serialized as querystring
 * params; the query key carries the same fields so each filter combo
 * gets its own cache entry.
 */
export function useContentListQuery(filters: ContentListFilters = {}) {
  const { contentType, q, page = 1, pageSize = 20 } = filters;
  return useQuery<ContentListResponse, Error>({
    queryKey: ["content", "list", { contentType, q, page, pageSize }],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/content", {
        params: {
          query: {
            content_type: contentType,
            q: q?.trim() ? q.trim() : undefined,
            page,
            page_size: pageSize,
          },
        },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}

export function useContentDetailQuery(contentId: string | null) {
  return useQuery<ContentDetailResponse, Error>({
    queryKey: ["content", "detail", contentId],
    enabled: Boolean(contentId),
    queryFn: async () => {
      const { data, error, response } = await api.GET("/content/{content_id}", {
        params: { path: { content_id: contentId as string } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}

export function useDeleteContentMutation() {
  const queryClient = useQueryClient();
  return useMutation<ContentDetailResponse, Error, string>({
    mutationFn: async (contentId) => {
      const { data, error, response } = await api.DELETE("/content/{content_id}", {
        params: { path: { content_id: contentId } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content", "list"] });
    },
  });
}

export function useRestoreContentMutation() {
  const queryClient = useQueryClient();
  return useMutation<ContentDetailResponse, Error, string>({
    mutationFn: async (contentId) => {
      const { data, error, response } = await api.POST("/content/{content_id}/restore", {
        params: { path: { content_id: contentId } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content", "list"] });
    },
  });
}
