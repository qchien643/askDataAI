import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from 'react';
import { useRouter } from 'next/router';

// ── Types ──
interface ConnectionInfo {
  connected: boolean;
  deployed: boolean;
  host: string;
  port: number;
  database: string;
  models_count: number;
}

interface ConnectionContextType {
  /** Current connection state */
  info: ConnectionInfo;
  /** True while polling or initial fetch is in progress */
  isLoading: boolean;
  /** True when knowledge/model changes need re-indexing */
  needsRedeploy: boolean;
  /** Re-fetch connection status from backend */
  refresh: () => Promise<void>;
  /** Mark that a re-deploy is needed (after knowledge/model edits) */
  markNeedsRedeploy: () => void;
  /** Clear the needsRedeploy flag (after successful deploy) */
  clearNeedsRedeploy: () => void;
}

const DEFAULT_INFO: ConnectionInfo = {
  connected: false,
  deployed: false,
  host: '',
  port: 0,
  database: '',
  models_count: 0,
};

const ConnectionContext = createContext<ConnectionContextType>({
  info: DEFAULT_INFO,
  isLoading: true,
  needsRedeploy: false,
  refresh: async () => {},
  markNeedsRedeploy: () => {},
  clearNeedsRedeploy: () => {},
});

// ── Constants ──
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
const POLL_INTERVAL = 10_000; // 10 seconds
const PUBLIC_PATHS = ['/setup', '/']; // Pages that don't need connection

// ── Provider ──
export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<ConnectionInfo>(DEFAULT_INFO);
  const [isLoading, setIsLoading] = useState(true);
  const [needsRedeploy, setNeedsRedeploy] = useState(false);
  const router = useRouter();

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/connections/status`);
      if (res.ok) {
        const data: ConnectionInfo = await res.json();
        setInfo(data);
      } else {
        setInfo(DEFAULT_INFO);
      }
    } catch {
      // Backend unreachable
      setInfo(DEFAULT_INFO);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Polling every 10 seconds
  useEffect(() => {
    const interval = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Auto-redirect to /setup when disconnected (only on protected pages)
  useEffect(() => {
    if (isLoading) return;
    const isPublic = PUBLIC_PATHS.includes(router.pathname);
    if (!info.connected && !isPublic) {
      router.replace('/setup');
    }
  }, [info.connected, isLoading, router.pathname]);

  const markNeedsRedeploy = useCallback(() => {
    setNeedsRedeploy(true);
  }, []);

  const clearNeedsRedeploy = useCallback(() => {
    setNeedsRedeploy(false);
  }, []);

  return (
    <ConnectionContext.Provider
      value={{
        info,
        isLoading,
        needsRedeploy,
        refresh: fetchStatus,
        markNeedsRedeploy,
        clearNeedsRedeploy,
      }}
    >
      {children}
    </ConnectionContext.Provider>
  );
}

// ── Hook ──
export function useConnection() {
  return useContext(ConnectionContext);
}
