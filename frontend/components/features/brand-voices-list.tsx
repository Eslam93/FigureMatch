// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useState } from "react";
import { toast } from "sonner";

import { BrandVoiceForm } from "@/components/features/brand-voice-form";
import { Button } from "@/components/ui/button";

import {
  type BrandVoice,
  useBrandVoicesQuery,
  useDeleteBrandVoiceMutation,
} from "@/lib/brand-voices/hooks";

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; voice: BrandVoice };

export function BrandVoicesList() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const list = useBrandVoicesQuery();
  const del = useDeleteBrandVoiceMutation();

  if (mode.kind !== "list") {
    return (
      <div className="space-y-4">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold">
            {mode.kind === "create" ? "New brand voice" : `Edit ${mode.voice.name}`}
          </h1>
          <p className="text-sm text-muted-foreground">
            Define how this brand sounds. The generator will follow these rules when you select this
            voice on the generate page.
          </p>
        </header>
        <BrandVoiceForm
          initial={mode.kind === "edit" ? mode.voice : null}
          onSaved={() => setMode({ kind: "list" })}
          onCancel={() => setMode({ kind: "list" })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Brand voices</h1>
          <p className="text-sm text-muted-foreground">
            Optional style presets you can attach to any generation.
          </p>
        </div>
        <Button onClick={() => setMode({ kind: "create" })} data-testid="bv-create">
          New brand voice
        </Button>
      </header>

      {list.isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : list.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {list.error.message}
        </p>
      ) : list.data && list.data.data.length === 0 ? (
        <div
          className="rounded-lg border border-dashed bg-card p-12 text-center"
          data-testid="bv-empty"
        >
          <p className="text-sm text-muted-foreground">
            No brand voices yet. Create one to start tuning generations to a specific tone.
          </p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="bv-list">
          {list.data?.data.map((voice) => (
            <li
              key={voice.id}
              className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-card p-4"
              data-testid={`bv-row-${voice.id}`}
            >
              <div className="min-w-0 space-y-1">
                <h3 className="font-semibold">{voice.name}</h3>
                {voice.description ? (
                  <p className="text-sm text-muted-foreground">{voice.description}</p>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  {voice.tone_descriptors.length ? voice.tone_descriptors.join(" · ") : "—"}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setMode({ kind: "edit", voice })}
                  data-testid={`bv-edit-${voice.id}`}
                >
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={del.isPending && del.variables === voice.id}
                  onClick={() =>
                    del.mutate(voice.id, {
                      onSuccess: () => toast.success("Brand voice deleted."),
                      onError: (err) => toast.error(err.message),
                    })
                  }
                  data-testid={`bv-delete-${voice.id}`}
                >
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
