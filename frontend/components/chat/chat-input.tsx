'use client'

import { useState } from 'react'
import { ArrowUpIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface ChatInputProps {
  onSend: (content: string) => void
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [value, setValue] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    onSend(value.trim())
    setValue('')
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 rounded-2xl border bg-card p-2 shadow-lg"
    >
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Ask about a bourbon..."
        className="h-11 flex-1 border-none bg-transparent shadow-none focus-visible:ring-0"
      />
      <Button
        type="submit"
        variant="ghost"
        size="icon"
        disabled={!value.trim()}
        aria-label="Send message"
        className="h-11 w-11 text-primary hover:text-primary"
      >
        <ArrowUpIcon className="size-5" />
      </Button>
    </form>
  )
}
