// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { useState } from "react";

import { ImproveResult } from "@/components/features/improve-result";
import { Alert, Button } from "@/components/ui/v2";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { IMPROVE_GOALS, type ImprovementGoal, useImproveMutation } from "@/lib/improver/hooks";

/**
 * Improver page form.
 *
 * Textarea for the original, goal picker, conditional `new_audience`
 * field when goal=audience_rewrite. Submit fires the two-call chain
 * server-side; the result panel renders before / after panes plus an
 * explanation block.
 */
export function ImproveForm() {
  const [originalText, setOriginalText] = useState("");
  const [goal, setGoal] = useState<ImprovementGoal>("persuasive");
  const [newAudience, setNewAudience] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const mutation = useImproveMutation();
  const isPending = mutation.isPending;
  const needsAudience = goal === "audience_rewrite";

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitError(null);
    if (originalText.trim().length < 10) {
      setSubmitError("Paste at least 10 characters to improve.");
      return;
    }
    if (needsAudience && !newAudience.trim()) {
      setSubmitError("Tell us who the new audience is.");
      return;
    }
    mutation.mutate({
      original_text: originalText,
      goal,
      new_audience: needsAudience ? newAudience : undefined,
    });
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Improve a piece of copy</h1>
        <p className="text-sm text-muted-foreground">
          Paste your draft, pick a goal, and the improver will analyze it and rewrite — side-by-side
          so you can see what changed.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="improve-original">
            Original text <span className="text-destructive">*</span>
          </Label>
          <textarea
            id="improve-original"
            value={originalText}
            onChange={(e) => setOriginalText(e.target.value)}
            disabled={isPending}
            placeholder="Paste your draft here…"
            className="min-h-[180px] w-full rounded-md border border-input bg-background p-3 text-sm"
            data-testid="improve-original"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="improve-goal">Goal</Label>
            <select
              id="improve-goal"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={goal}
              onChange={(e) => setGoal(e.target.value as ImprovementGoal)}
              disabled={isPending}
              data-testid="improve-goal"
            >
              {IMPROVE_GOALS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          {needsAudience ? (
            <div className="space-y-2">
              <Label htmlFor="improve-audience">New audience</Label>
              <Input
                id="improve-audience"
                value={newAudience}
                onChange={(e) => setNewAudience(e.target.value)}
                placeholder="e.g. senior backend engineers"
                disabled={isPending}
                data-testid="improve-audience"
              />
            </div>
          ) : null}
        </div>

        {submitError ? (
          <Alert variant="destructive" data-testid="improve-validation">
            {submitError}
          </Alert>
        ) : null}

        {mutation.isError ? (
          <Alert
            variant="destructive"
            onDismiss={() => mutation.reset()}
            data-testid="improve-error"
          >
            {mutation.error.message}
          </Alert>
        ) : null}

        <Button type="submit" variant="brand" loading={isPending} data-testid="improve-submit">
          Improve
        </Button>
      </form>

      {mutation.isSuccess ? <ImproveResult data={mutation.data} /> : null}
    </div>
  );
}
