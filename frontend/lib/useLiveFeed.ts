"use client";

import { useEffect, useRef, useState } from "react";
import { getToken, LiveEvent, WS_URL } from "./api";

/**
 * Opens a WebSocket to the API and calls onEvent for every message.
 * Reconnects automatically (1s, 2s, 4s ... up to 15s) if the connection drops.
 * Returns whether the socket is currently connected, for the "Live" badge.
 */
export function useLiveFeed(onEvent: (event: LiveEvent) => void): boolean {
  const [connected, setConnected] = useState(false);

  // keep the latest callback in a ref so the socket never has to reconnect
  // just because the component re-rendered
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let attempt = 0;

    const connect = () => {
      socket = new WebSocket(`${WS_URL}/ws?token=${encodeURIComponent(token)}`);
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      socket.onmessage = (message) => {
        try {
          handler.current(JSON.parse(message.data) as LiveEvent);
        } catch {
          /* ignore malformed messages */
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) {
          attempt += 1;
          retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt, 15000));
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return connected;
}
