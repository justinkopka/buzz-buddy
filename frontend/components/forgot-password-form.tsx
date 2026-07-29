'use client'

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createClient } from '@/lib/supabase/client'
import { useState } from "react";

export function ForgotPasswordForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)

  async function submitEmailForPasswordReset(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()

    setError('')
   
    const {data, error} = await supabase.auth.resetPasswordForEmail( 
      email,
      {redirectTo: `${window.location.origin}/update-password`}
    )

    if (!error) {
      setIsSubmitted(true)
    } else {
      setError(error.message)
    }
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle>Forgot Your Password?</CardTitle>
        </CardHeader>
        {!isSubmitted ? (
          <>
          <CardHeader>
            <CardDescription>Please enter the email you used to create your account.</CardDescription>
          </CardHeader>
            <CardContent>
              <form onSubmit={submitEmailForPasswordReset}>
                <FieldGroup>
                  <Field>
                      <FieldLabel htmlFor="email">Email</FieldLabel>
                      <Input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="m@example.com"
                        required
                      />
                    </Field>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                  <Field>
                    <Button type="submit">Submit</Button>
                  </Field>
                </FieldGroup>
              </form>
            </CardContent>
          </>
        ) : (
          <>
          <CardHeader>
            <CardDescription>
              We sent a confirmation to <strong>{email}</strong>. Check your email to reset your password.
            </CardDescription>
          </CardHeader>
          </>
        )}
      </Card>
    </div>
  )
}