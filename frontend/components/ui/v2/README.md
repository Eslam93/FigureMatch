# FigureMatch UI — v2 design system

Drop-in successor to `components/ui/*` and the inline-styled blocks scattered across `components/features/*`. v2 is **additive** — nothing in v1 changes, and the two systems coexist while features migrate.

> **TL;DR**: install the tokens (1 paste), merge the Tailwind fragment (1 paste), import from `@/components/ui/v2`, and incrementally replace v1 imports as you touch each feature.

---

## 1. What's in the box

| Primitive                                                                      | Purpose                                                                                    | Replaces                                                                                                |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `Button`                                                                       | All buttons. Adds `loading`, `leftIcon`, `rightIcon`, brand/success variants.              | v1 `Button` + manual `"Generating…"` strings                                                            |
| `Input`                                                                        | Text input with branded focus + `aria-invalid` styling.                                    | v1 `Input`                                                                                              |
| `Textarea`                                                                     | Matches Input styling.                                                                     | Inline `<textarea className="min-h-[180px] w-full rounded-md …">` in `improve-form`, `brand-voice-form` |
| `Select`                                                                       | Native `<select>` styled to match Input.                                                   | Inline `<select className="h-9 …">` in 4 files                                                          |
| `Label`                                                                        | Adds `required` and `optional` props.                                                      | v1 `Label` + manual `<span className="text-destructive">*</span>`                                       |
| `FormField`                                                                    | Composes label + control + error message + ARIA wiring.                                    | The 10-line `<div className="space-y-2">` pattern repeated 12+ times                                    |
| `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardBody`, `CardFooter` | Card surfaces with `flat`/`raised`/`floating` elevation and optional `interactive` styles. | `rounded-lg border bg-card p-4/p-6` repeated 8+ times                                                   |
| `Alert`                                                                        | `info`, `success`, `warning`, `destructive` banners with icons.                            | Destructive banner (5×) + amber warning banner (3×)                                                     |
| `Badge`                                                                        | Status pills (`success`, `warning`, `info`, `destructive`, `brand`, `neutral`, `outline`). | Inline amber pill in `content-card.tsx`                                                                 |
| `EmptyState`                                                                   | Dashed-border empty block with icon + title + description + CTA.                           | `content-list`, `brand-voices-list` empty blocks                                                        |
| `Dialog` + parts                                                               | Modal with focus trap, focus restore, Escape, click-outside.                               | v1 `Modal`                                                                                              |
| `Tabs`                                                                         | Generic, ARIA-correct tablist controlled by a value.                                       | Bespoke `ContentTypeTabs` in `generate-form.tsx`                                                        |
| `Spinner`, `Skeleton`, `StagedLoader`                                          | Loading affordances.                                                                       | Inline `"Loading…"` text and feature-specific `StagedLoader`                                            |

Every primitive uses `cn()` from `@/lib/utils` and CSS variables, so v1 and v2 share the same theme.

---

## 2. Install

### 2.1 Install missing dependency

The new `Button` and `Spinner` use `lucide-react` (already in `package.json`). Nothing else to install. If you adopt Radix Dialog or Radix Tabs later, add them — v2 deliberately avoids new deps.

### 2.2 Append v2 tokens to `app/globals.css`

```css
/* app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ⬇ keep all your existing :root and .dark blocks above this line ⬇ */

@import "../components/ui/v2/tokens.css";
```

Or paste the contents of [`tokens.css`](./tokens.css) at the bottom of `globals.css`. Either works.

### 2.3 Merge the Tailwind fragment

```ts
// tailwind.config.ts
import type { Config } from "tailwindcss";

import { v2Tokens } from "@/components/ui/v2/tailwind.tokens";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        // ⬇ your existing v1 colors stay here ⬇
        border: "hsl(var(--border))",
        // … (unchanged)

        // ⬇ v2 colors merged in ⬇
        ...v2Tokens.colors,
      },
      boxShadow: v2Tokens.boxShadow,
      transitionDuration: v2Tokens.transitionDuration,
      transitionTimingFunction: v2Tokens.transitionTimingFunction,
      ringColor: v2Tokens.ringColor,
      ringOffsetColor: v2Tokens.ringOffsetColor,
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};

export default config;
```

### 2.4 Verify

```bash
cd frontend
pnpm typecheck
pnpm build
```

The build should pass without touching any feature file — v1 still works, v2 is just available to import.

---

## 3. Usage

### 3.1 The single biggest win: `FormField`

**Before** (`generate-form.tsx`, lines 73–89):

```tsx
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
```

**After**:

```tsx
import { FormField, Input } from "@/components/ui/v2";

<FormField label="Topic" required error={errors.topic?.message}>
  <Input
    placeholder="e.g. How small teams should evaluate AI tools"
    disabled={isPending}
    data-testid="generate-topic"
    {...register("topic")}
  />
</FormField>;
```

`FormField` wires `id`, `htmlFor`, `aria-invalid`, `aria-describedby`, and `role="alert"` for you.

### 3.2 Buttons with loading state

**Before**:

```tsx
<Button disabled={isPending}>{isPending ? "Generating…" : "Generate"}</Button>
```

**After**:

```tsx
<Button loading={isPending} variant="brand">
  Generate
</Button>
```

Width stays stable, focus ring uses `--brand`, spinner is a real `<Loader2>` not a string.

### 3.3 Banners

**Before** (`generate-form.tsx`, line 144):

```tsx
{
  mutation.isError ? (
    <p
      className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
      role="alert"
      data-testid="generate-error"
    >
      {mutation.error.message}
      <Button variant="link" onClick={() => mutation.reset()}>
        Dismiss
      </Button>
    </p>
  ) : null;
}
```

**After**:

```tsx
import { Alert } from "@/components/ui/v2";

{
  mutation.isError ? (
    <Alert variant="destructive" onDismiss={() => mutation.reset()} data-testid="generate-error">
      {mutation.error.message}
    </Alert>
  ) : null;
}
```

The amber "fallback rendering" banner gets the same treatment with `variant="warning"`.

### 3.4 Cards

**Before** (`content-card.tsx`):

```tsx
<article className="group flex cursor-pointer flex-col gap-3 rounded-lg border bg-card p-4 transition hover:border-primary/60 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
```

**After**:

```tsx
import { Card } from "@/components/ui/v2";

<Card interactive elevation="flat" role="button" tabIndex={0} onClick={…}>
```

### 3.5 Dialog

The v1 `Modal` works but lacks a focus trap. The v2 `Dialog` is a drop-in upgrade:

```tsx
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogBody,
  DialogFooter,
  DialogCloseButton,
  Button,
} from "@/components/ui/v2";

<Dialog open={open} onOpenChange={setOpen} aria-label="Content detail">
  <DialogHeader>
    <DialogTitle>{item.topic}</DialogTitle>
    <DialogCloseButton onClose={() => setOpen(false)} />
  </DialogHeader>
  <DialogBody>{children}</DialogBody>
  <DialogFooter>
    <Button variant="outline" onClick={() => setOpen(false)}>
      Close
    </Button>
  </DialogFooter>
</Dialog>;
```

---

## 4. Migration plan

Adopt v2 incrementally — there is no "v2 day" deadline. Suggested order, smallest blast radius first:

1. **Auth pages** (`app/(auth)/login`, `app/(auth)/register`) — small forms, ideal place to validate `FormField` + `Button.loading` in your app.
2. **brand-voice-form.tsx** — replaces the inline textarea + form pattern.
3. **generate-form.tsx** — biggest payoff. Replace `ContentTypeTabs` with `<Tabs>`, every field with `FormField`, the error block with `<Alert>`, and `StagedLoader` import path.
4. **improve-form.tsx** — same shape as generate-form.
5. **content-list.tsx** — `EmptyState`, `Card`, `Select` for the filter.
6. **content-card.tsx** — `Card interactive`, `Badge` for the fallback pill.
7. **content-detail-dialog.tsx** — swap `Modal` for `Dialog`. Test focus-trap behaviour with keyboard.
8. **brand-voices-list.tsx** — `EmptyState`, `Card`.
9. **image-panel.tsx**, **generate-result.tsx**, **improve-result.tsx** — `Card`, `Alert`, `Select`.

When all features have moved off `components/ui/{button,input,label,modal}.tsx`, delete the v1 files and rename `components/ui/v2/*` → `components/ui/*`. The barrel `index.ts` makes that a 1-line import find-and-replace.

### Codemod-friendly find-and-replace

| Find                                                                                             | Replace                                      |
| ------------------------------------------------------------------------------------------------ | -------------------------------------------- |
| `from "@/components/ui/button"`                                                                  | `from "@/components/ui/v2"`                  |
| `from "@/components/ui/input"`                                                                   | `from "@/components/ui/v2"`                  |
| `from "@/components/ui/label"`                                                                   | `from "@/components/ui/v2"`                  |
| `from "@/components/ui/modal"` then `Modal` → `Dialog`, `onClose` → `onOpenChange`, `open` stays | manual review (Modal has 1 prop name change) |

---

## 5. Token taxonomy

v2 introduces five layers on top of the v1 slate base. None replaces a v1 token.

| Layer          | Tokens                                                                                                 | Use it for                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Brand          | `--brand`, `--brand-foreground`, `--brand-subtle`, `--brand-subtle-foreground`                         | Primary CTAs, branded surfaces, the focus ring on interactive elements |
| Semantic state | `--success`, `--warning`, `--info` (each with `-foreground` and `-subtle`/`-subtle-foreground`)        | Alerts, badges, toast variants                                         |
| Surface        | `--surface-raised`, `--surface-sunken`, `--surface-overlay`                                            | Layered surfaces (e.g. `DialogFooter` uses `surface-sunken`)           |
| Elevation      | `--shadow-sm`, `--shadow-md`, `--shadow-lg` (Tailwind `shadow-elev-sm/md/lg`)                          | Cards (`elevation="raised"`), dialogs                                  |
| Motion         | `--duration-fast/base/slow`, `--ease-out`, `--ease-in-out` (Tailwind `duration-fast`, `ease-out-soft`) | All transitions in v2 use these                                        |

Reduced-motion is honoured automatically — `prefers-reduced-motion: reduce` collapses every duration to `0.01ms`.

---

## 6. Conventions

- **All variant systems use `cva`.** Adding a new variant means editing one file and one map.
- **All classnames go through `cn()`.** No `+`-concatenation, no template-literal soup.
- **State on the element, not in JS.** Error styles are driven by `aria-invalid`. Loading is driven by `data-loading` and `aria-busy`. This means form libraries (react-hook-form, anything) wire up by setting one ARIA attribute.
- **`"use client"` only where required.** Pure-presentational primitives (`Input`, `Textarea`, `Select`, `Card`, `Badge`, `Skeleton`, `EmptyState`, `Spinner`) are server-compatible. Anything with `useState`/`useEffect`/Radix is client.
- **No new dependencies.** v2 ships on the existing `@radix-ui/react-label`, `@radix-ui/react-slot`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react` set.

---

## 7. Accessibility checklist

| Concern             | How v2 handles it                                                                                                |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Focus visible       | Every interactive element renders a 2px branded ring on `:focus-visible` via `ring-focus` + `ring-offset-focus`. |
| Required fields     | `<Label required>` renders a `*` marked `aria-hidden`; the field uses native `required`.                         |
| Error announcements | `FormField` sets `aria-invalid`, links the error via `aria-describedby`, and gives the error `role="alert"`.     |
| Dialog focus trap   | `Dialog` traps Tab/Shift-Tab, restores focus on close, locks body scroll, and reacts to Escape.                  |
| Alert severity      | `Alert` defaults to `role="alert"` for destructive/warning, `role="status"` for info/success.                    |
| Reduced motion      | Token-driven; respected without per-component code.                                                              |

---

## 8. Why this shape

A few decisions worth flagging:

- **No Radix Tabs / Radix Select.** Current usages are simple. Adding two packages for one disabled-tooltip behaviour isn't worth it. Both primitives mirror Radix's prop names, so swapping later is a structural edit, not a rewrite.
- **`FormField` clones the child element.** `React.cloneElement` is the simplest way to inject ARIA without forcing every control to accept a prop bag. The trade-off — children must be a single React element — is fine for our forms.
- **Custom Dialog instead of Radix Dialog.** Avoids the extra dep; the focus trap is ~20 lines. If product later needs nested dialogs or portal-out-of-iframe, swap the implementation behind the same JSX.
- **Brand-tinted focus ring.** The v1 `--ring` is near-black (`222 47% 11%`), which is invisible against the dark primary button. v2's `--focus-ring` is the brand hue, distinct from any surface.

---

## 9. Open questions

- The brand hue in `tokens.css` is a placeholder blue (`221 83% 53%`). Swap it for the real FigureMatch brand once design has picked one.
- `Surface` tokens are defined but only used by `DialogFooter` so far — expand if/when we adopt a layered layout pattern (e.g. a settings page with grouped surfaces).
- Consider a `Toast` primitive that wraps `sonner` so feature code doesn't import `sonner` directly. Out of scope for this slice.
