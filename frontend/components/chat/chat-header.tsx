'use client'

import { useEffect, useState } from 'react'
import { HomeIcon, SettingsIcon } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { getRolesFromToken } from '@/lib/auth'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export function ChatHeader() {
  const supabase = createClient()
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setIsAdmin(getRolesFromToken(session.access_token).includes('admin'))
      }
    })
  }, [supabase])

  async function signOut() {
    await supabase.auth.signOut()
    window.location.href = '/login'
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b px-4">
      <Link
        href="/"
        className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-muted"
        aria-label="Back to chat"
      >
        <HomeIcon className="size-5" />
      </Link>

      <div className="flex items-center gap-2">
        <Image src="/logo.png" alt="" width={24} height={24} className="rounded-md" />
        <span className="text-sm font-semibold">BuzzBuddy</span>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-sm font-medium hover:bg-muted/80"
            aria-label="Open menu"
          >
            <SettingsIcon className="size-5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem>Settings</DropdownMenuItem>
          {isAdmin && (
            <DropdownMenuItem onClick={() => (window.location.href = '/admin')}>
              Admin
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onClick={signOut}
          >
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
