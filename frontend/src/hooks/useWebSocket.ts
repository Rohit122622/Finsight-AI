import { useEffect, useRef, useState, useCallback } from "react";
import { getAccessToken } from "../api/client";
import { extractErrorMessage } from "../utils/errors";
import type { LiveAgentStatusEvent, JobProgressEvent } from "../types";

export interface WebSocketHookState {
  isConnected: boolean;
  agentEvents: LiveAgentStatusEvent[];
  latestJobProgress: JobProgressEvent | null;
  lastError: string | null;
  sendAction: (action: string, payload?: Record<string, any>) => void;
}

export function useSessionWebSocket(sessionId: string | undefined): WebSocketHookState {
  const [isConnected, setIsConnected] = useState(false);
  const [agentEvents, setAgentEvents] = useState<LiveAgentStatusEvent[]>([]);
  const [latestJobProgress, setLatestJobProgress] = useState<JobProgressEvent | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isUnmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (!sessionId || isUnmountedRef.current) return;
    const token = getAccessToken();
    if (!token) return;

    
    if (socketRef.current) {
      try {
        socketRef.current.close(1000, "Reconnecting");
      } catch {
        
      }
      socketRef.current = null;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/sessions/${encodeURIComponent(sessionId)}/ws?token=${encodeURIComponent(token)}`;

    try {
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (isUnmountedRef.current) {
          socket.close(1000, "Unmounted");
          return;
        }
        setIsConnected(true);
        setLastError(null);
        
        try {
          socket.send(JSON.stringify({ action: "subscribe", payload: { channels: ["all"] } }));
        } catch {
          
        }
      };

      socket.onmessage = (event) => {
        if (isUnmountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          const type = data?.type;

          if (type === "agent_milestone" || type === "agent_status") {
            const agentEvent: LiveAgentStatusEvent = {
              agent_name: data.payload?.agent_name || "Agent",
              status: data.payload?.milestone || data.payload?.status || "PROCESSING",
              session_id: data.session_id || sessionId,
              timestamp: data.timestamp || new Date().toISOString(),
              details: data.payload?.details || data.payload,
            };
            setAgentEvents((prev) => [agentEvent, ...prev.slice(0, 49)]);
          } else if (type === "job_progress") {
            setLatestJobProgress({
              job_id: data.payload?.job_id,
              progress_percent: data.payload?.progress_percent ?? 0,
              current_step: data.payload?.current_step ?? "PROCESSING",
              status: data.payload?.status ?? "PROCESSING",
              message: data.payload?.message,
              events: data.payload?.events,
            });
          }
        } catch {
          
        }
      };

      socket.onerror = () => {
        if (!isUnmountedRef.current) {
          setIsConnected(false);
        }
      };

      socket.onclose = (ev) => {
        if (isUnmountedRef.current) return;
        setIsConnected(false);
        
        if (ev.code !== 1000 && ev.code !== 4001 && ev.code !== 4003 && ev.code !== 4004) {
          reconnectTimeoutRef.current = window.setTimeout(() => {
            if (!isUnmountedRef.current) {
              connect();
            }
          }, 3000);
        }
      };
    } catch (err: unknown) {
      if (!isUnmountedRef.current) {
        setLastError(extractErrorMessage(err, "Failed to initialize WebSocket"));
      }
    }
  }, [sessionId]);

  useEffect(() => {
    isUnmountedRef.current = false;
    connect();

    
    const pingInterval = setInterval(() => {
      if (
        !isUnmountedRef.current &&
        socketRef.current &&
        socketRef.current.readyState === WebSocket.OPEN
      ) {
        try {
          socketRef.current.send(JSON.stringify({ action: "ping", payload: { client_time: Date.now() } }));
        } catch {
          
        }
      }
    }, 20_000);

    return () => {
      isUnmountedRef.current = true;
      clearInterval(pingInterval);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        try {
          socketRef.current.close(1000, "Component unmounted");
        } catch {
          
        }
        socketRef.current = null;
      }
    };
  }, [connect]);

  const sendAction = useCallback((action: string, payload: Record<string, any> = {}) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      try {
        socketRef.current.send(JSON.stringify({ action, payload }));
      } catch (err: unknown) {
        console.warn("[WebSocket sendAction failed]:", err);
      }
    }
  }, []);

  return {
    isConnected,
    agentEvents,
    latestJobProgress,
    lastError,
    sendAction,
  };
}

