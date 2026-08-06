'use client'

import { useState } from 'react'
import { ChatHeader } from '@/components/chat/chat-header'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessages } from '@/components/chat/chat-messages'
import { streamChatMessage } from '@/lib/api'
import type { ChatMessage } from '@/lib/types'

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])

  async function handleSend(content: string) {
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    }
    const assistantId = crypto.randomUUID()
    const placeholder: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
    }

    const history = [...messages, userMessage].map(({ role, content }) => ({ role, content }))
    setMessages((prev) => [...prev, userMessage, placeholder])

    try {
      for await (const chunk of streamChatMessage(history)) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m
          )
        )
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: 'The assistant is unavailable right now — check your connection and try again.' }
            : m
        )
      )
    }
  }

  return (
    <div className="flex flex-col h-svh overflow-hidden">
      <ChatHeader />

      <div className="relative flex-1 min-h-0">
        <ChatMessages messages={messages} />

        <div className="absolute inset-x-0 bottom-0 px-4 pb-4">
          <div className="mx-auto w-full max-w-3xl">
            <ChatInput onSend={handleSend} />
          </div>
        </div>
      </div>
    </div>
  )
}
