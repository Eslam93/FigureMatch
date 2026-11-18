// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { Alert, Button } from "@/components/ui/v2";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegisterMutation } from "@/lib/auth/hooks";
import { type RegisterInput, registerSchema } from "@/lib/auth/schemas";

export default function RegisterPage() {
  const mutation = useRegisterMutation();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", full_name: "" },
  });

  const onSubmit = (data: RegisterInput) => {
    mutation.mutate(data);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-bold">Create account</h1>
        <p className="text-sm text-muted-foreground">A 60-second setup. No credit card.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="full_name">Full name</Label>
          <Input
            id="full_name"
            autoComplete="name"
            disabled={isSubmitting || mutation.isPending}
            aria-invalid={errors.full_name ? true : undefined}
            {...register("full_name")}
          />
          {errors.full_name ? (
            <p className="text-sm text-destructive" role="alert">
              {errors.full_name.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            disabled={isSubmitting || mutation.isPending}
            aria-invalid={errors.email ? true : undefined}
            {...register("email")}
          />
          {errors.email ? (
            <p className="text-sm text-destructive" role="alert">
              {errors.email.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            disabled={isSubmitting || mutation.isPending}
            aria-invalid={errors.password ? true : undefined}
            {...register("password")}
          />
          {errors.password ? (
            <p className="text-sm text-destructive" role="alert">
              {errors.password.message}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              At least 8 characters, including a letter and a digit.
            </p>
          )}
        </div>

        {mutation.isError ? <Alert variant="destructive">{mutation.error.message}</Alert> : null}

        <Button
          type="submit"
          variant="brand"
          className="w-full"
          disabled={isSubmitting}
          loading={mutation.isPending}
        >
          Create account
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
