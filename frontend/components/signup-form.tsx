'use client'

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createClient } from '@/lib/supabase/client'
import { useState } from "react";

export function SignupForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)

  async function signUp(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()

    if (password !== confirmPassword) {
        setError('Passwords do not match')
        return
    }
    setError('')
   
    const {data, error} = await supabase.auth.signUp({ 
      email: email, 
      password: password 
    })

    if (!error) {
      setIsSubmitted(true)
    } else {
      setError(error.message)
    }
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        {isSubmitted ? (
          <CardHeader>
              <CardTitle>Check your email</CardTitle>
              <CardDescription>
                We sent a confirmation to <strong>{email}</strong>. Check your email to activate your account.
              </CardDescription>
            </CardHeader>
        ) : (
          <>
            <CardHeader>
              <CardTitle>Create a new account</CardTitle>
              <CardDescription>
                Enter your email below
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={signUp}>
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
                  <Field>
                    <FieldLabel htmlFor="password">Password</FieldLabel>
                    <Input 
                      id="password" 
                      type="password" 
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required 
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="confirmPassword">Confirm Password</FieldLabel>
                    <Input 
                      id="confirmPassword" 
                      type="password" 
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required 
                    />
                  </Field>
                  {error && <p className="text-sm text-destructive">{error}</p>}
                  <Field>
                    <Button type="submit">Sign Up</Button>
                  </Field>
                </FieldGroup>
              </form>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  )
}
