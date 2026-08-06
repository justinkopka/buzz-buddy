import { createClient } from '@/lib/supabase/client'

export async function* streamChatMessage(
  messages: { role: 'user' | 'assistant'; content: string }[]
): AsyncGenerator<string> {
  const supabase = createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Not authenticated')
  }

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/chat-message`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ messages }),
  })

  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    yield decoder.decode(value, { stream: true })
  }
}
