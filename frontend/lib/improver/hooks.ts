// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { generateErrorMessage } from "@/lib/content/hooks";

import type { components } from "@/types/api";

export type ImprovementGoal = components["schemas"]["ImprovementGoal"];
export type ImprovementResponse = components["schemas"]["ImprovementResponse"];
export type ImproveRequest = components["schemas"]["ImproveRequest"];

export const IMPROVE_GOALS: ReadonlyArray<{ value: ImprovementGoal; label: string }> = [
  { value: "shorter", label: "Shorter" },
  { value: "persuasive", label: "More persuasive" },
  { value: "formal", label: "More formal" },
  { value: "seo", label: "SEO-optimized" },
  { value: "audience_rewrite", label: "Rewrite for a new audience" },
];

/**
 * Submit an improve request. Success payload is the full
 * `ImprovementResponse` — caller renders `improved_text` next to the
 * original plus the explanation bullets and changes_summary.
 */
export function useImproveMutation() {
  const queryClient = useQueryClient();
  return useMutation<ImprovementResponse, Error, ImproveRequest>({
    mutationFn: async (input) => {
      const body: ImproveRequest = {
        original_text: input.original_text.trim(),
        goal: input.goal,
        new_audience: input.new_audience?.trim() ? input.new_audience.trim() : undefined,
      };
      const { data, error, response } = await api.POST("/improve", { body });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["improvements", "list"] });
    },
  });
}
