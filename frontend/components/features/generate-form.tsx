// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Alert, Button } from "@/components/ui/v2";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { useBrandVoicesQuery } from "@/lib/brand-voices/hooks";
import { useGenerateMutation, type GenerateResponse } from "@/lib/content/hooks";
import {
  CONTENT_TYPE_OPTIONS,
  type GenerateInput,
  generateSchema,
} from "@/lib/validation/generate";

import { GenerateResult } from "./generate-result";
import { StagedLoader } from "./staged-loader";

import type { components } from "@/types/api";

type ContentType = components["schemas"]["ContentType"];

/**
 * Generate form — content-type picker + topic/tone/audience.
 *
 * Slice 1 only enables blog_post. The other tabs render disabled so
 * the UI doesn't change shape when Slice 2 widens support.
 */
export function GenerateForm() {
  const mutation = useGenerateMutation();
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<GenerateInput>({
    resolver: zodResolver(generateSchema),
    defaultValues: {
      content_type: "blog_post",
      topic: "",
      tone: "",
      target_audience: "",
      brand_voice_id: "",
    },
  });

  const selectedContentType = watch("content_type");
  const isPending = mutation.isPending;
  const brandVoices = useBrandVoicesQuery();

  const onSubmit = (data: GenerateInput) => {
    mutation.mutate(data);
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Generate content</h1>
        <p className="text-sm text-muted-foreground">
          Pick a content type, describe what you need, and we&apos;ll draft it.
        </p>
      </header>

      <ContentTypeTabs
        value={selectedContentType}
        disabled={isPending}
        onChange={(value) => setValue("content_type", value, { shouldValidate: true })}
      />

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="topic">
            Topic <span className="text-destructive">*</span>
          </Label>
          <Input
            id="topic"
            placeholder="e.g. How small teams should evaluate AI tools"
            disabled={isPending}
            aria-invalid={errors.topic ? true : undefined}
            data-testid="generate-topic"
            {...register("topic")}
          />
          {errors.topic ? (
            <p className="text-sm text-destructive" role="alert">
              {errors.topic.message}
            </p>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="tone">Tone</Label>
            <Input
              id="tone"
              placeholder="informative, witty, no-nonsense…"
              disabled={isPending}
              data-testid="generate-tone"
              {...register("tone")}
            />
            {errors.tone ? (
              <p className="text-sm text-destructive" role="alert">
                {errors.tone.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="target_audience">Audience</Label>
            <Input
              id="target_audience"
              placeholder="engineering managers, marketers…"
              disabled={isPending}
              data-testid="generate-audience"
              {...register("target_audience")}
            />
            {errors.target_audience ? (
              <p className="text-sm text-destructive" role="alert">
                {errors.target_audience.message}
              </p>
            ) : null}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="brand_voice_id">Brand voice (optional)</Label>
          <select
            id="brand_voice_id"
            disabled={isPending || brandVoices.isPending}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            data-testid="generate-brand-voice"
            {...register("brand_voice_id")}
          >
            <option value="">No brand voice</option>
            {brandVoices.data?.data.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.name}
              </option>
            ))}
          </select>
        </div>

        {mutation.isError ? (
          <Alert
            variant="destructive"
            onDismiss={() => mutation.reset()}
            data-testid="generate-error"
          >
            {mutation.error.message}
          </Alert>
        ) : null}

        <Button
          type="submit"
          variant="brand"
          className="w-full sm:w-auto"
          loading={isPending}
          data-testid="generate-submit"
        >
          Generate
        </Button>
      </form>

      <StagedLoader active={isPending} />

      {mutation.isSuccess ? <ResultBlock data={mutation.data} /> : null}
    </div>
  );
}

function ContentTypeTabs({
  value,
  disabled,
  onChange,
}: {
  value: ContentType;
  disabled: boolean;
  onChange: (next: ContentType) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Content type"
      className="flex flex-wrap gap-2"
      data-testid="content-type-tabs"
    >
      {CONTENT_TYPE_OPTIONS.map((opt) => {
        const isActive = opt.value === value;
        const isClickable = opt.enabled && !disabled;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-disabled={!opt.enabled}
            title={opt.enabled ? undefined : opt.tooltip}
            disabled={!isClickable}
            onClick={() => isClickable && onChange(opt.value)}
            data-testid={`content-type-tab-${opt.value}`}
            className={
              "rounded-md border px-3 py-1.5 text-sm transition " +
              (isActive
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card hover:bg-accent") +
              (!opt.enabled ? "cursor-not-allowed opacity-50" : "")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ResultBlock({ data }: { data: GenerateResponse }) {
  return <GenerateResult data={data} />;
}
