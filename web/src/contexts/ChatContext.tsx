/**
 * ChatContext — Persists chat threads across page navigation.
 *
 * By lifting thread state into a React context at the _app level,
 * the chat data survives when navigating between /home, /modeling, /settings, etc.
 */
import { createContext, useContext, useState, ReactNode } from 'react';
import type { DebugTrace } from '@/utils/types';

export interface Msg {
  role: 'user' | 'ai';
  text: string;
  sql?: string;
  columns?: string[];
  rows?: any[];
  rowCount?: number;
  explanation?: string;
  valid?: boolean;
  pipelineInfo?: {
    reasoning_steps?: string[];
    columns_pruned?: number;
    candidates_generated?: number;
    voting_method?: string;
    glossary_matches?: number;
    guardian_passed?: boolean;
    sub_intent?: string;
    // Stage 0.5: Conversation Context metadata
    session_id?: string;
    enriched_question?: string;
    was_enriched?: boolean;
  };
  debugTrace?: DebugTrace;
  // Thought panel — pipeline stage trace saved per message
  thoughtSteps?: { stage: string; label: string; detail?: string }[];
  thoughtSeconds?: number;
  // Chart data
  chartSpec?: Record<string, any>;
  chartData?: Record<string, any>[];
  chartReasoning?: string;
  chartType?: string;
  chartLoading?: boolean;
  chartError?: string;
  originalQuestion?: string;
}

export interface Thread {
  id: string;
  title: string;
  messages: Msg[];
  session_id?: string;  // mem0 session ID — persisted across turns for context
}

interface ChatContextType {
  threads: Thread[];
  setThreads: React.Dispatch<React.SetStateAction<Thread[]>>;
  activeId: string | null;
  setActiveId: React.Dispatch<React.SetStateAction<string | null>>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  return (
    <ChatContext.Provider value={{ threads, setThreads, activeId, setActiveId }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat(): ChatContextType {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return ctx;
}
