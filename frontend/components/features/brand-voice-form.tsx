// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/v2";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  type BrandVoice,
  type BrandVoiceCreate,
  useCreateBrandVoiceMutation,
  useUpdateBrandVoiceMutation,
} from "@/lib/brand-voices/hooks";

interface Props {
  initial?: BrandVoice | null;
  onSaved: () => void;
  onCancel: () => void;
}

function csvToList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Single form used for both create and edit — the difference is which
 * mutation fires on submit.
 */
export function BrandVoiceForm({ initial, onSaved, onCancel }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tone, setTone] = useState("");
  const [banned, setBanned] = useState("");
  const [audience, setAudience] = useState("");
  const [sample, setSample] = useState("");

  useEffect(() => {
    setName(initial?.name ?? "");
    setDescription(initial?.description ?? "");
    setTone((initial?.tone_descriptors ?? []).join(", "));
    setBanned((initial?.banned_words ?? []).join(", "));
    setAudience(initial?.target_audience ?? "");
    setSample(initial?.sample_text ?? "");
  }, [initial]);

  const create = useCreateBrandVoiceMutation();
  const update = useUpdateBrandVoiceMutation();
  const isPending = create.isPending || update.isPending;
  const isEdit = Boolean(initial?.id);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (name.trim().length < 1) {
      toast.error("Give the brand voice a name.");
      return;
    }
    const payload: BrandVoiceCreate = {
      name: name.trim(),
      description: description.trim() || null,
      tone_descriptors: csvToList(tone),
      banned_words: csvToList(banned),
      sample_text: sample.trim() || null,
      target_audience: audience.trim() || null,
    };
    if (isEdit && initial) {
      update.mutate(
        { id: initial.id, updates: payload },
        {
          onSuccess: () => {
            toast.success("Brand voice updated.");
            onSaved();
          },
          onError: (err) => toast.error(err.message),
        },
      );
    } else {
      create.mutate(payload, {
        onSuccess: () => {
          toast.success("Brand voice created.");
          onSaved();
        },
        onError: (err) => toast.error(err.message),
      });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" data-testid="brand-voice-form">
      <div className="space-y-2">
        <Label htmlFor="bv-name">
          Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="bv-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isPending}
          data-testid="bv-name"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="bv-description">Description</Label>
        <Input
          id="bv-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isPending}
          placeholder="One sentence about how this brand sounds."
          data-testid="bv-description"
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="bv-tone">Tone descriptors (comma-separated)</Label>
          <Input
            id="bv-tone"
            value={tone}
            onChange={(e) => setTone(e.target.value)}
            disabled={isPending}
            placeholder="direct, warm, specific"
            data-testid="bv-tone"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="bv-banned">Banned phrases (comma-separated)</Label>
          <Input
            id="bv-banned"
            value={banned}
            onChange={(e) => setBanned(e.target.value)}
            disabled={isPending}
            placeholder="leverage, synergy, game-changer"
            data-testid="bv-banned"
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="bv-audience">Brand audience</Label>
        <Input
          id="bv-audience"
          value={audience}
          onChange={(e) => setAudience(e.target.value)}
          disabled={isPending}
          placeholder="senior engineers, startup founders…"
          data-testid="bv-audience"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="bv-sample">Sample copy</Label>
        <textarea
          id="bv-sample"
          value={sample}
          onChange={(e) => setSample(e.target.value)}
          disabled={isPending}
          className="min-h-[120px] w-full rounded-md border border-input bg-background p-3 text-sm"
          placeholder="Paste 1–3 paragraphs the model can mimic without copying verbatim."
          data-testid="bv-sample"
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" variant="brand" loading={isPending} data-testid="bv-submit">
          {isEdit ? "Save changes" : "Create"}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
