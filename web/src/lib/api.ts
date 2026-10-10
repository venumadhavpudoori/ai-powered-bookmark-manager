/** API client for communicating with the FastAPI backend. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_V1 = `${API_BASE}/api/v1`;

// ── Types ────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Tag {
  id: string;
  name: string;
}

export interface BookmarkTag {
  tag: Tag;
  source: "ai" | "user";
}

export interface Bookmark {
  id: string;
  url: string;
  canonical_url: string;
  title: string | null;
  description: string | null;
  summary: string | null;
  key_takeaways: string[] | null;
  notes: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  collection_id: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
  tags: BookmarkTag[];
}

export interface BookmarkList {
  items: Bookmark[];
  total: number;
  page: number;
  size: number;
}

export interface Collection {
  id: string;
  name: string;
  created_at: string;
}

export interface SearchResult {
  bookmark: Bookmark;
  score: number;
  excerpt: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
}

export interface BookmarkStatus {
  bookmark_id: string;
  status: string;
  error_message: string | null;
  job_status: string | null;
  job_stage: string | null;
  attempt_count: number | null;
}

// ── HTTP Helpers ─────────────────────────────────────────

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_V1}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Auth ─────────────────────────────────────────────────

export async function register(
  email: string,
  password: string,
  displayName?: string
): Promise<User> {
  return request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const res = await request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("token", res.access_token);
  return res;
}

export function logout(): void {
  localStorage.removeItem("token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// ── Bookmarks ────────────────────────────────────────────

export async function createBookmark(data: {
  url: string;
  title?: string;
  notes?: string;
  collection_id?: string;
  tags?: string[];
}): Promise<Bookmark> {
  return request<Bookmark>("/bookmarks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listBookmarks(params?: {
  page?: number;
  size?: number;
  collection_id?: string;
  tag?: string;
  status?: string;
  archived?: boolean;
}): Promise<BookmarkList> {
  const search = new URLSearchParams();
  if (params?.page) search.set("page", String(params.page));
  if (params?.size) search.set("size", String(params.size));
  if (params?.collection_id) search.set("collection_id", params.collection_id);
  if (params?.tag) search.set("tag", params.tag);
  if (params?.status) search.set("status", params.status);
  if (params?.archived !== undefined)
    search.set("archived", String(params.archived));

  const qs = search.toString();
  return request<BookmarkList>(`/bookmarks${qs ? `?${qs}` : ""}`);
}

export async function getBookmark(id: string): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}`);
}

export async function updateBookmark(
  id: string,
  data: Partial<{
    title: string;
    notes: string;
    collection_id: string | null;
    archived: boolean;
    summary: string;
  }>
): Promise<Bookmark> {
  return request<Bookmark>(`/bookmarks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteBookmark(id: string): Promise<void> {
  return request<void>(`/bookmarks/${id}`, { method: "DELETE" });
}

export async function reprocessBookmark(
  id: string
): Promise<BookmarkStatus> {
  return request<BookmarkStatus>(`/bookmarks/${id}/process`, {
    method: "POST",
  });
}

export async function getBookmarkStatus(
  id: string
): Promise<BookmarkStatus> {
  return request<BookmarkStatus>(`/bookmarks/${id}/status`);
}

// ── Search ───────────────────────────────────────────────

export async function searchBookmarks(
  query: string,
  params?: { tag?: string; collection_id?: string; limit?: number }
): Promise<SearchResponse> {
  const search = new URLSearchParams({ q: query });
  if (params?.tag) search.set("tag", params.tag);
  if (params?.collection_id)
    search.set("collection_id", params.collection_id);
  if (params?.limit) search.set("limit", String(params.limit));

  return request<SearchResponse>(`/search?${search.toString()}`);
}

// ── Tags ─────────────────────────────────────────────────

export async function listTags(): Promise<Tag[]> {
  return request<Tag[]>("/tags");
}

export async function createTag(name: string): Promise<Tag> {
  return request<Tag>("/tags", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteTag(id: string): Promise<void> {
  return request<void>(`/tags/${id}`, { method: "DELETE" });
}

export async function addTagToBookmark(
  tagId: string,
  bookmarkId: string
): Promise<void> {
  return request<void>(`/tags/${tagId}/bookmarks/${bookmarkId}`, {
    method: "POST",
  });
}

export async function removeTagFromBookmark(
  tagId: string,
  bookmarkId: string
): Promise<void> {
  return request<void>(`/tags/${tagId}/bookmarks/${bookmarkId}`, {
    method: "DELETE",
  });
}

// ── Collections ──────────────────────────────────────────

export async function listCollections(): Promise<Collection[]> {
  return request<Collection[]>("/collections");
}

export async function createCollection(name: string): Promise<Collection> {
  return request<Collection>("/collections", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateCollection(
  id: string,
  name: string
): Promise<Collection> {
  return request<Collection>(`/collections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteCollection(id: string): Promise<void> {
  return request<void>(`/collections/${id}`, { method: "DELETE" });
}
