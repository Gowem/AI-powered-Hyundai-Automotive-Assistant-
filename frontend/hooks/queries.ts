"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ConversationDetail, ConversationList, DocumentList, User } from "@/lib/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<User>("/api/auth/me"), staleTime: 5 * 60_000 });
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<ConversationList>("/api/chat/conversations?limit=100"),
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ["conversation", id],
    queryFn: () => api<ConversationDetail>(`/api/chat/conversations/${id}`),
    enabled: !!id,
    staleTime: Infinity,
  });
}

export type DocumentFilters = { q?: string; vehicle_model?: string; status?: string };

export function useDocuments(filters: DocumentFilters = {}) {
  const params = new URLSearchParams({ limit: "200" });
  Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
  return useQuery({
    queryKey: ["documents", filters],
    queryFn: () => api<DocumentList>(`/api/documents?${params.toString()}`),
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.status === "queued" || d.status === "processing") ? 3000 : false,
  });
}

export function useVehicleModels() {
  return useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api<{ models: string[] }>("/api/documents/vehicles"),
    staleTime: Infinity,
  });
}
