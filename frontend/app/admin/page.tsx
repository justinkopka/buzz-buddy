import { ChatHeader } from '@/components/chat/chat-header'

export default function AdminPage() {
  return (
    <div className="flex flex-col h-svh overflow-hidden">
      <ChatHeader />
      <div className="flex flex-1 items-center justify-center">
        <h1 className="text-lg font-semibold">Admin Panel</h1>
      </div>
    </div>
  )
}
