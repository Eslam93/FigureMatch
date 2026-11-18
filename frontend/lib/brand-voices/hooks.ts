// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { generateErrorMessage } from "@/lib/content/hooks";

import type { components } from "@/types/api";

export type BrandVoice = components["schemas"]["BrandVoiceResponse"];
export type BrandVoiceCreate = components["schemas"]["BrandVoiceCreate"];
export type BrandVoiceUpdate = components["schemas"]["BrandVoiceUpdate"];

const LIST_KEY = ["brand-voices", "list"] as const;

export function useBrandVoicesQuery() {
  return useQuery<{ data: BrandVoice[] }, Error>({
    queryKey: LIST_KEY,
    queryFn: async () => {
      const { data, error, response } = await api.GET("/brand-voices");
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}

export function useCreateBrandVoiceMutation() {
  const queryClient = useQueryClient();
  return useMutation<BrandVoice, Error, BrandVoiceCreate>({
    mutationFn: async (input) => {
      const { data, error, response } = await api.POST("/brand-voices", { body: input });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useUpdateBrandVoiceMutation() {
  const queryClient = useQueryClient();
  return useMutation<BrandVoice, Error, { id: string; updates: BrandVoiceUpdate }>({
    mutationFn: async ({ id, updates }) => {
      const { data, error, response } = await api.PATCH("/brand-voices/{voice_id}", {
        params: { path: { voice_id: id } },
        body: updates,
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useDeleteBrandVoiceMutation() {
  const queryClient = useQueryClient();
  return useMutation<BrandVoice, Error, string>({
    mutationFn: async (id) => {
      const { data, error, response } = await api.DELETE("/brand-voices/{voice_id}", {
        params: { path: { voice_id: id } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}
