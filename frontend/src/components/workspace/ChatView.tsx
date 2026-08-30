import React from 'react';
import { MessagingBar } from '../chat/MessagingBar';
import { ChatStream } from '../chat/ChatStream';
import { ExecutionStatusBar } from '../chat/ExecutionStatusBar';

// The artifact card renderer moved to components/chat/ArtifactCard.tsx, next to
// ChatStream which actually mounts it. It used to be defined here and imported
// by nothing, which is why backend cards — charts included — never rendered.

export const ChatView: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col h-full bg-[#f4f1ea] overflow-hidden">
      <ChatStream />
      <ExecutionStatusBar />
      <MessagingBar />
    </div>
  );
};
