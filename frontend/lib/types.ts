export type User = { id: string; email: string; full_name: string | null };

export type DocumentStatus = "pending_upload" | "queued" | "processing" | "ready" | "failed";

export type DocumentItem = {
  id: string;
  display_name: string;
  original_filename: string;
  vehicle_model: string;
  model_year: string | null;
  uploaded_at: string;
  processed_at: string | null;
  status: DocumentStatus;
  status_detail: string | null;
  page_count: number | null;
  chunk_count: number;
  file_size_bytes: number;
  owner_is_me: boolean;
};

export type DocumentList = { items: DocumentItem[]; total: number; ready_count: number };

export type UploadUrlResponse = {
  document_id: string;
  path: string;
  token: string | null;
  mode: "supabase" | "local";
  upload_url: string | null;
};

export type Source = {
  n: number;
  document_id: string;
  document_name: string;
  vehicle_model: string;
  page: number;
  snippet: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  intent: string | null;
  created_at: string;
};

export type Conversation = { id: string; title: string; created_at: string; updated_at: string };
export type ConversationDetail = Conversation & { messages: ChatMessage[] };
export type ConversationList = { items: Conversation[]; total: number };

export type ChatAnswer = {
  message_id: string;
  user_message_id: string;
  content: string;
  sources: Source[];
  intent: string | null;
  conversation_title: string;
};

export type StreamStage = "understanding" | "retrieving" | "writing";
