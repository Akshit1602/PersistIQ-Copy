import { ChatStream } from '../chat/ChatStream'
import { ExecutionStatusBar } from '../chat/ExecutionStatusBar'
import { MessagingBar } from '../chat/MessagingBar'

export function ChatView() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ChatStream />
      <ExecutionStatusBar />
      <MessagingBar />
    </div>
  )
}
