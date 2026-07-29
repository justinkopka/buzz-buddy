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
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { createClient } from '@/lib/supabase/client'
import { useState } from "react";

export function UpdatePasswordForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const supabase = createClient()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')

  async function updatePassword(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()

    if (password !== confirmPassword) {
        setError('Passwords do not match')
        return
    }
    setError('')
   
    const {data, error} = await supabase.auth.updateUser({  
      password: password 
    })

    if (!error) {
      window.location.href = '/login'
    } else {
      setError(error.message)
    }
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader>
            <CardTitle>Create a new password</CardTitle>
            <CardDescription>
                Enter your new password below
            </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={updatePassword}>
            <FieldGroup>
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
                <Button type="submit">Submit</Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}