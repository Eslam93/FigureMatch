// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { generateErrorMessage } from "@/lib/content/hooks";

import type { components } from "@/types/api";

export type GeneratedImage = components["schemas"]["GeneratedImage"];
export type ImageListResponse = components["schemas"]["ImageListResponse"];
export type ImageStyle = components["schemas"]["ImageStyle"];

export const IMAGE_STYLES: ReadonlyArray<{ value: ImageStyle; label: string }> = [
  { value: "photorealistic", label: "Photorealistic" },
  { value: "illustration", label: "Illustration" },
  { value: "minimalist", label: "Minimalist" },
  { value: "3d_render", label: "3D render" },
  { value: "watercolor", label: "Watercolor" },
  { value: "cinematic", label: "Cinematic" },
];

/**
 * List every image version generated for a content piece, newest
 * first. Gated on the content id so the hook is safe to call with
 * `null` (the query won't fire).
 */
export function useImageListQuery(contentId: string | null) {
  return useQuery<ImageListResponse, Error>({
    queryKey: ["content", "images", contentId],
    enabled: Boolean(contentId),
    queryFn: async () => {
      const { data, error, response } = await api.GET("/content/{content_id}/images", {
        params: { path: { content_id: contentId as string } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}

export interface ImageGenerateInput {
  contentId: string;
  style: ImageStyle;
}

/**
 * Generate (or regenerate) the image for a content piece. On success we
 * write the new image directly into the list cache and flip any prior
 * `is_current=true` row to `false`. Pure invalidation caused a visible
 * gap: the panel uses `list.data` to decide what to render, so during
 * the refetch window the newly-generated image was momentarily absent
 * and the panel flashed empty before the refetch landed. Optimistic
 * cache write closes that gap.
 */
export function useImageGenerateMutation() {
  const queryClient = useQueryClient();
  return useMutation<GeneratedImage, Error, ImageGenerateInput>({
    mutationFn: async ({ contentId, style }) => {
      const { data, error, response } = await api.POST("/content/{content_id}/image", {
        params: { path: { content_id: contentId } },
        body: { style },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data.image;
    },
    onSuccess: (image, { contentId }) => {
      queryClient.setQueryData<ImageListResponse>(["content", "images", contentId], (prev) => {
        const prior = prev?.data ?? [];
        const demoted = prior.map((row) => (row.is_current ? { ...row, is_current: false } : row));
        return { data: [image, ...demoted] };
      });
    },
  });
}
