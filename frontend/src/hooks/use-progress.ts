"use client";
import { useEffect, useRef, useState } from "react";
import { io } from "socket.io-client";
import { api, getToken } from "@/services/api";
import type { Investigation } from "@/types/investigation";

export function useProgress(userId: string, onUpdate: (row: Investigation) => void, onReconnect: () => void) {
  const [connection, setConnection] = useState("Connecting to live updates…");
  const callbacks = useRef({onUpdate, onReconnect});
  callbacks.current = {onUpdate, onReconnect};
  useEffect(() => {
    let active = true;
    let socket: ReturnType<typeof io> | undefined;
    async function connect() {
      try {
        const {data} = await api.get<{realtime_url: string}>("/auth/me");
        if (!active) return;
        if (!data.realtime_url) throw new Error("Realtime is not configured");
        const channel = `investigation:${userId}`;
        socket = io(data.realtime_url, {
          auth: (cb) => {
            // Validate/refresh the short-lived token again on each reconnect.
            void api.get("/auth/me").then(() => cb({token: getToken()}))
              .catch(() => cb({token: ""}));
          },
          reconnectionAttempts: 5,
        });
        socket.on("connect", () => {
          socket?.timeout(10000).emit("realtime:subscribe", {channel},
            (err: Error | null, response: {ok?: boolean}) => {
              if (!active) return;
              setConnection(!err && response?.ok ? "Live updates connected" : "Live updates unavailable — use Refresh history");
              callbacks.current.onReconnect();
            });
        });
        socket.on("investigation_progress", (message: Investigation & {meta?: {channel?: string; senderType?: string}}) => {
          if (!message || message.meta?.channel !== channel || message.meta?.senderType !== "system") return;
          if (typeof message.id !== "string" || typeof message.revision !== "number" || !message.progress) return;
          callbacks.current.onUpdate(message);
        });
        socket.on("disconnect", () => {if (active) setConnection("Live updates disconnected — results will still appear when the request completes");});
        socket.on("connect_error", () => {if (active) setConnection("Live updates unavailable — use Refresh history");});
        socket.on("realtime:error", () => {if (active) setConnection("Live subscription denied — check InsForge channel policies");});
      } catch {if (active) setConnection("Live updates unavailable — use Refresh history");}
    }
    void connect();
    return () => {active = false; socket?.disconnect();};
  }, [userId]);
  return connection;
}
