"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Bookmark,
  Collection,
  Tag,
  SearchResult,
  listBookmarks,
  createBookmark,
  updateBookmark,
  deleteBookmark,
  reprocessBookmark,
  searchBookmarks,
  listCollections,
  createCollection,
  deleteCollection,
  listTags,
  createTag,
  addTagToBookmark,
  removeTagFromBookmark,
  isAuthenticated,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const router = useRouter();
  const { logout } = useAuth();

  // State
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null);
  const [viewArchived, setViewArchived] = useState(false);

  // Modals & Panels
  const [showAddModal, setShowAddModal] = useState(false);
  const [showNewCollectionInput, setShowNewCollectionInput] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [selectedBookmark, setSelectedBookmark] = useState<Bookmark | null>(null);

  // Form states for Add Bookmark
  const [newUrl, setNewUrl] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [newCollectionId, setNewCollectionId] = useState("");
  const [newTagsStr, setNewTagsStr] = useState("");
  const [submittingAdd, setSubmittingAdd] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Detail Modal Edit States
  const [detailSummary, setDetailSummary] = useState("");
  const [detailNotes, setDetailNotes] = useState("");
  const [detailTitle, setDetailTitle] = useState("");
  const [newTagInput, setNewTagInput] = useState("");
  const [savingDetail, setSavingDetail] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  // Check auth
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    }
  }, [router]);

  // Load initial data
  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [bmRes, colRes, tagRes] = await Promise.all([
        listBookmarks({
          archived: viewArchived,
          collection_id: selectedCollection || undefined,
          tag: selectedTag || undefined,
          status: selectedStatus || undefined,
          size: 100,
        }),
        listCollections(),
        listTags(),
      ]);
      setBookmarks(bmRes.items);
      setCollections(colRes);
      setTags(tagRes);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load dashboard data");
      }
    } finally {
      setLoading(false);
    }
  }, [viewArchived, selectedCollection, selectedTag, selectedStatus]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-polling for active background jobs
  useEffect(() => {
    const hasActiveJobs = bookmarks.some(
      (b) => b.status === "pending" || b.status === "processing"
    );

    if (!hasActiveJobs) return;

    const interval = setInterval(async () => {
      try {
        const bmRes = await listBookmarks({
          archived: viewArchived,
          collection_id: selectedCollection || undefined,
          tag: selectedTag || undefined,
          status: selectedStatus || undefined,
          size: 100,
        });
        setBookmarks(bmRes.items);

        // Update selected bookmark in modal if open
        if (selectedBookmark) {
          const updated = bmRes.items.find((b) => b.id === selectedBookmark.id);
          if (updated) setSelectedBookmark(updated);
        }
      } catch {
        // Silently ignore polling errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [bookmarks, viewArchived, selectedCollection, selectedTag, selectedStatus, selectedBookmark]);

  // Search handler
  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    try {
      setIsSearching(true);
      const res = await searchBookmarks(searchQuery.trim(), {
        tag: selectedTag || undefined,
        collection_id: selectedCollection || undefined,
        limit: 30,
      });
      setSearchResults(res.results);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setIsSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setSearchResults(null);
  };

  // Add bookmark handler
  const handleAddBookmark = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUrl.trim()) return;

    try {
      setSubmittingAdd(true);
      setAddError(null);
      const tagList = newTagsStr
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const created = await createBookmark({
        url: newUrl.trim(),
        title: newTitle.trim() || undefined,
        notes: newNotes.trim() || undefined,
        collection_id: newCollectionId || undefined,
        tags: tagList.length > 0 ? tagList : undefined,
      });

      setBookmarks((prev) => [created, ...prev]);
      setShowAddModal(false);
      setNewUrl("");
      setNewTitle("");
      setNewNotes("");
      setNewCollectionId("");
      setNewTagsStr("");
      fetchData();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setAddError(err.message);
      } else {
        setAddError("Failed to save bookmark");
      }
    } finally {
      setSubmittingAdd(false);
    }
  };

  // Retry failed bookmark
  const handleRetry = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      setRetryingId(id);
      await reprocessBookmark(id);
      setBookmarks((prev) =>
        prev.map((b) => (b.id === id ? { ...b, status: "pending", error_message: null } : b))
      );
      if (selectedBookmark?.id === id) {
        setSelectedBookmark((prev) =>
          prev ? { ...prev, status: "pending", error_message: null } : null
        );
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetryingId(null);
    }
  };

  // Archive / Unarchive
  const handleToggleArchive = async (bookmark: Bookmark, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      const updated = await updateBookmark(bookmark.id, {
        archived: !bookmark.archived,
      });
      setBookmarks((prev) =>
        prev
          .map((b) => (b.id === bookmark.id ? updated : b))
          .filter((b) => (viewArchived ? b.archived : !b.archived))
      );
      if (selectedBookmark?.id === bookmark.id) {
        setSelectedBookmark(updated);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Archive failed");
    }
  };

  // Delete bookmark
  const handleDeleteBookmark = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!confirm("Are you sure you want to delete this bookmark?")) return;

    try {
      await deleteBookmark(id);
      setBookmarks((prev) => prev.filter((b) => b.id !== id));
      if (searchResults) {
        setSearchResults((prev) => prev?.filter((r) => r.bookmark.id !== id) || null);
      }
      if (selectedBookmark?.id === id) {
        setSelectedBookmark(null);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  // Open detail modal
  const openDetail = (bookmark: Bookmark) => {
    setSelectedBookmark(bookmark);
    setDetailTitle(bookmark.title || "");
    setDetailSummary(bookmark.summary || "");
    setDetailNotes(bookmark.notes || "");
  };

  // Save changes in detail modal
  const handleSaveDetail = async () => {
    if (!selectedBookmark) return;
    try {
      setSavingDetail(true);
      const updated = await updateBookmark(selectedBookmark.id, {
        title: detailTitle,
        summary: detailSummary,
        notes: detailNotes,
      });
      setSelectedBookmark(updated);
      setBookmarks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update bookmark");
    } finally {
      setSavingDetail(false);
    }
  };

  // Add tag to selected bookmark
  const handleAddTagToDetail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedBookmark || !newTagInput.trim()) return;

    try {
      const tagText = newTagInput.trim();
      let tagObj = tags.find((t) => t.name.toLowerCase() === tagText.toLowerCase());
      if (!tagObj) {
        tagObj = await createTag(tagText);
        setTags((prev) => [...prev, tagObj!]);
      }

      await addTagToBookmark(tagObj.id, selectedBookmark.id);
      setNewTagInput("");

      // Update local bookmark tags
      const newBookmarkTag = { tag: tagObj, source: "user" as const };
      const updated = {
        ...selectedBookmark,
        tags: [...selectedBookmark.tags.filter((t) => t.tag.id !== tagObj!.id), newBookmarkTag],
      };
      setSelectedBookmark(updated);
      setBookmarks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add tag");
    }
  };

  // Remove tag from selected bookmark
  const handleRemoveTag = async (tagId: string) => {
    if (!selectedBookmark) return;
    try {
      await removeTagFromBookmark(tagId, selectedBookmark.id);
      const updated = {
        ...selectedBookmark,
        tags: selectedBookmark.tags.filter((t) => t.tag.id !== tagId),
      };
      setSelectedBookmark(updated);
      setBookmarks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove tag");
    }
  };

  // Collection creation
  const handleCreateCollection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCollectionName.trim()) return;
    try {
      const created = await createCollection(newCollectionName.trim());
      setCollections((prev) => [...prev, created]);
      setNewCollectionName("");
      setShowNewCollectionInput(false);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create collection");
    }
  };

  // Collection deletion
  const handleDeleteCollection = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Delete this collection? Bookmarks will remain uncategorized.")) return;
    try {
      await deleteCollection(id);
      setCollections((prev) => prev.filter((c) => c.id !== id));
      if (selectedCollection === id) setSelectedCollection(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete collection");
    }
  };

  // Display items: either search results or filtered bookmarks
  const displayItems = useMemo(() => {
    if (searchResults !== null) {
      return searchResults.map((r) => ({
        bookmark: r.bookmark,
        excerpt: r.excerpt,
        score: r.score,
      }));
    }
    return bookmarks.map((b) => ({
      bookmark: b,
      excerpt: null as string | null,
      score: null as number | null,
    }));
  }, [searchResults, bookmarks]);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex flex-col text-[var(--color-text)]">
      {/* ── Top Navigation Bar ──────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-md px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-2xl font-bold tracking-tight">
            <span className="gradient-text">RecallAI</span>
          </Link>
          <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-primary)]/20 text-[var(--color-primary)] border border-[var(--color-primary)]/30 font-medium">
            Personal Engine
          </span>
        </div>

        {/* Global Semantic Search Bar */}
        <form onSubmit={handleSearch} className="flex-1 max-w-2xl relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by meaning... (e.g. 'python async tutorial', 'machine learning tools')"
            className="w-full pl-10 pr-24 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)] transition"
          />
          <span className="absolute left-3.5 top-2.5 text-[var(--color-text-muted)] text-sm">
            🔍
          </span>
          <div className="absolute right-2 top-1.5 flex items-center gap-1">
            {searchQuery && (
              <button
                type="button"
                onClick={clearSearch}
                className="text-xs px-2 py-1 rounded text-[var(--color-text-muted)] hover:text-white"
              >
                Clear
              </button>
            )}
            <button
              type="submit"
              disabled={isSearching}
              className="text-xs px-3 py-1 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white font-medium rounded-lg shadow-sm"
            >
              {isSearching ? "Searching..." : "Search"}
            </button>
          </div>
        </form>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white font-semibold text-sm rounded-xl shadow-lg shadow-[var(--color-primary)]/20 transition hover:-translate-y-0.5"
          >
            <span>+</span>
            <span>Add Bookmark</span>
          </button>
          <button
            onClick={logout}
            className="px-3 py-2 text-sm border border-[var(--color-border)] hover:border-[var(--color-danger)] hover:text-[var(--color-danger)] rounded-xl transition"
          >
            Log Out
          </button>
        </div>
      </header>

      {/* ── Main Workspace Layout ───────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar Navigation */}
        <aside className="w-64 border-r border-[var(--color-border)] bg-[var(--color-surface)]/40 p-5 flex flex-col gap-6 overflow-y-auto">
          {/* Main Views */}
          <div className="space-y-1">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
              Views
            </div>
            <button
              onClick={() => {
                setViewArchived(false);
                setSelectedCollection(null);
                setSelectedTag(null);
                setSelectedStatus(null);
                clearSearch();
              }}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition ${
                !viewArchived && !selectedCollection && !selectedTag && !selectedStatus && !searchResults
                  ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)] font-semibold"
                  : "text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
              }`}
            >
              <span>📚 All Bookmarks</span>
              <span className="text-xs opacity-75">{bookmarks.length}</span>
            </button>
            <button
              onClick={() => {
                setViewArchived(true);
                setSelectedCollection(null);
                setSelectedTag(null);
                setSelectedStatus(null);
                clearSearch();
              }}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition ${
                viewArchived
                  ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)] font-semibold"
                  : "text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
              }`}
            >
              <span>🗄️ Archive</span>
            </button>
          </div>

          {/* Status Filters */}
          <div className="space-y-1">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
              Status
            </div>
            {["completed", "processing", "pending", "failed"].map((st) => (
              <button
                key={st}
                onClick={() => {
                  setSelectedStatus(selectedStatus === st ? null : st);
                  clearSearch();
                }}
                className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-xs capitalize transition ${
                  selectedStatus === st
                    ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)] font-semibold"
                    : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                <span>{st}</span>
                {st === "failed" && (
                  <span className="w-2 h-2 rounded-full bg-[var(--color-failed)]" />
                )}
                {st === "processing" && (
                  <span className="w-2 h-2 rounded-full bg-[var(--color-processing)] animate-pulse" />
                )}
                {st === "completed" && (
                  <span className="w-2 h-2 rounded-full bg-[var(--color-completed)]" />
                )}
                {st === "pending" && (
                  <span className="w-2 h-2 rounded-full bg-[var(--color-pending)]" />
                )}
              </button>
            ))}
          </div>

          {/* Collections Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
                Collections
              </span>
              <button
                onClick={() => setShowNewCollectionInput(!showNewCollectionInput)}
                className="text-xs text-[var(--color-primary)] hover:underline"
              >
                + New
              </button>
            </div>

            {showNewCollectionInput && (
              <form onSubmit={handleCreateCollection} className="flex gap-1 mb-2">
                <input
                  type="text"
                  value={newCollectionName}
                  onChange={(e) => setNewCollectionName(e.target.value)}
                  placeholder="Collection name"
                  autoFocus
                  className="w-full text-xs px-2 py-1 bg-[var(--color-bg)] border border-[var(--color-border)] rounded focus:outline-none focus:border-[var(--color-primary)]"
                />
                <button
                  type="submit"
                  className="text-xs px-2 py-1 bg-[var(--color-primary)] text-white rounded"
                >
                  ✓
                </button>
              </form>
            )}

            <div className="space-y-1">
              {collections.map((col) => (
                <div
                  key={col.id}
                  onClick={() => {
                    setSelectedCollection(selectedCollection === col.id ? null : col.id);
                    clearSearch();
                  }}
                  className={`group flex items-center justify-between px-3 py-1.5 rounded-lg text-sm cursor-pointer transition ${
                    selectedCollection === col.id
                      ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)] font-semibold"
                      : "text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
                  }`}
                >
                  <span className="truncate">📁 {col.name}</span>
                  <button
                    onClick={(e) => handleDeleteCollection(col.id, e)}
                    className="opacity-0 group-hover:opacity-100 text-[var(--color-danger)] text-xs hover:font-bold px-1"
                    title="Delete collection"
                  >
                    ×
                  </button>
                </div>
              ))}
              {collections.length === 0 && (
                <div className="text-xs text-[var(--color-text-muted)] italic px-3 py-1">
                  No collections yet
                </div>
              )}
            </div>
          </div>

          {/* Tags Cloud / Filter */}
          <div className="space-y-2">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
              Tags
            </div>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setSelectedTag(selectedTag === t.name ? null : t.name);
                    clearSearch();
                  }}
                  className={`text-xs px-2.5 py-1 rounded-full border transition ${
                    selectedTag === t.name
                      ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)]"
                      : "bg-[var(--color-surface)] border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)]"
                  }`}
                >
                  #{t.name}
                </button>
              ))}
              {tags.length === 0 && (
                <div className="text-xs text-[var(--color-text-muted)] italic">
                  Tags will appear here after AI extraction
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* ── Content View ────────────────────────────────────── */}
        <main className="flex-1 p-8 overflow-y-auto">
          {/* Active Filter Bar */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">
                {searchResults !== null
                  ? `Search Results for "${searchQuery}"`
                  : viewArchived
                  ? "Archived Bookmarks"
                  : selectedCollection
                  ? `Collection: ${collections.find((c) => c.id === selectedCollection)?.name || ""}`
                  : selectedTag
                  ? `Tagged with #${selectedTag}`
                  : selectedStatus
                  ? `Status: ${selectedStatus}`
                  : "All Bookmarks"}
              </h2>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                Showing {displayItems.length} item{displayItems.length === 1 ? "" : "s"}
              </p>
            </div>

            {(selectedCollection || selectedTag || selectedStatus || searchResults) && (
              <button
                onClick={() => {
                  setSelectedCollection(null);
                  setSelectedTag(null);
                  setSelectedStatus(null);
                  clearSearch();
                }}
                className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] hover:text-white"
              >
                Reset Filters
              </button>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 rounded-xl bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm">
              {error}
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="glass-card p-6 h-52 animate-pulse bg-[var(--color-surface)]/50" />
              ))}
            </div>
          )}

          {/* Empty State */}
          {!loading && displayItems.length === 0 && (
            <div className="glass-card p-12 text-center max-w-md mx-auto my-12 animate-fade-in">
              <div className="text-4xl mb-4">🔖</div>
              <h3 className="text-lg font-semibold mb-2">No bookmarks found</h3>
              <p className="text-sm text-[var(--color-text-muted)] mb-6">
                {searchResults !== null
                  ? "Try adjusting your search query to find related items."
                  : "Save your first link to start building your AI-indexed knowledge base."}
              </p>
              <button
                onClick={() => setShowAddModal(true)}
                className="px-6 py-2.5 bg-[var(--color-primary)] text-white text-sm font-semibold rounded-xl hover:bg-[var(--color-primary-hover)] transition"
              >
                Add Bookmark
              </button>
            </div>
          )}

          {/* Bookmarks Grid */}
          {!loading && displayItems.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {displayItems.map(({ bookmark, excerpt, score }) => {
                const domain = (() => {
                  try {
                    return new URL(bookmark.url).hostname;
                  } catch {
                    return bookmark.url;
                  }
                })();

                return (
                  <div
                    key={bookmark.id}
                    onClick={() => openDetail(bookmark)}
                    className="glass-card p-5 flex flex-col justify-between hover:border-[var(--color-primary)]/50 cursor-pointer transition-all duration-200 hover:-translate-y-1 shadow-md hover:shadow-xl relative group"
                  >
                    <div>
                      {/* Card Header: Domain & Status */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <span className="text-xs font-medium text-[var(--color-accent)] truncate max-w-[160px]">
                          {domain}
                        </span>

                        <div className="flex items-center gap-2">
                          {score !== null && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-accent)]/20 text-[var(--color-accent)] font-mono">
                              Match: {(score * 100).toFixed(0)}%
                            </span>
                          )}
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-medium capitalize ${
                              bookmark.status === "completed"
                                ? "bg-[var(--color-completed)]/20 text-[var(--color-completed)]"
                                : bookmark.status === "processing"
                                ? "bg-[var(--color-processing)]/20 text-[var(--color-primary)] animate-pulse"
                                : bookmark.status === "failed"
                                ? "bg-[var(--color-failed)]/20 text-[var(--color-failed)]"
                                : "bg-[var(--color-pending)]/20 text-[var(--color-pending)]"
                            }`}
                          >
                            {bookmark.status}
                          </span>
                        </div>
                      </div>

                      {/* Title */}
                      <h3 className="font-semibold text-base mb-2 line-clamp-2 leading-snug group-hover:text-[var(--color-primary)] transition">
                        {bookmark.title || domain}
                      </h3>

                      {/* Excerpt (from search) or AI Summary */}
                      {excerpt ? (
                        <p className="text-xs text-[var(--color-accent)]/90 bg-[var(--color-surface-hover)] p-2 rounded-lg mb-3 line-clamp-3 italic font-sans border border-[var(--color-accent)]/20">
                          &quot;{excerpt}&quot;
                        </p>
                      ) : (
                        <p className="text-xs text-[var(--color-text-muted)] line-clamp-3 mb-3 leading-relaxed">
                          {bookmark.summary ||
                            (bookmark.status === "processing"
                              ? "AI is extracting content, analyzing themes, and generating semantic embeddings..."
                              : bookmark.status === "pending"
                              ? "Queued for processing..."
                              : bookmark.status === "failed"
                              ? `Extraction error: ${bookmark.error_message || "Unknown error"}`
                              : "No summary available")}
                        </p>
                      )}

                      {/* Tags */}
                      {bookmark.tags && bookmark.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {bookmark.tags.slice(0, 4).map((bt) => (
                            <span
                              key={bt.tag.id}
                              className={`text-[10px] px-2 py-0.5 rounded-full border ${
                                bt.source === "ai"
                                  ? "bg-[var(--color-primary)]/10 text-[var(--color-primary)] border-[var(--color-primary)]/30"
                                  : "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/30"
                              }`}
                            >
                              #{bt.tag.name}
                            </span>
                          ))}
                          {bookmark.tags.length > 4 && (
                            <span className="text-[10px] text-[var(--color-text-muted)] self-center">
                              +{bookmark.tags.length - 4}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Card Footer: Metadata & Quick Actions */}
                    <div className="pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                      <div className="flex items-center gap-2">
                        {bookmark.collection_id && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] border border-[var(--color-border)]">
                            📁 {collections.find((c) => c.id === bookmark.collection_id)?.name}
                          </span>
                        )}
                        <span>
                          {new Date(bookmark.created_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })}
                        </span>
                      </div>

                      <div className="flex items-center gap-1">
                        {bookmark.status === "failed" && (
                          <button
                            onClick={(e) => handleRetry(bookmark.id, e)}
                            disabled={retryingId === bookmark.id}
                            className="px-2 py-1 text-[11px] bg-[var(--color-failed)]/20 hover:bg-[var(--color-failed)]/30 text-[var(--color-failed)] rounded font-medium transition"
                            title="Retry extraction"
                          >
                            {retryingId === bookmark.id ? "Retrying..." : "↺ Retry"}
                          </button>
                        )}
                        <a
                          href={bookmark.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="p-1 hover:text-white rounded"
                          title="Open original link"
                        >
                          ↗
                        </a>
                        <button
                          onClick={(e) => handleToggleArchive(bookmark, e)}
                          className="p-1 hover:text-white rounded"
                          title={bookmark.archived ? "Unarchive" : "Archive"}
                        >
                          {bookmark.archived ? "↩" : "🗄️"}
                        </button>
                        <button
                          onClick={(e) => handleDeleteBookmark(bookmark.id, e)}
                          className="p-1 hover:text-[var(--color-danger)] rounded"
                          title="Delete"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>

      {/* ── Add Bookmark Modal ───────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="glass-card p-6 w-full max-w-lg animate-fade-in shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">Add New Bookmark</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-lg text-[var(--color-text-muted)] hover:text-white"
              >
                ✕
              </button>
            </div>

            {addError && (
              <div className="mb-4 p-3 rounded-lg bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm">
                {addError}
              </div>
            )}

            <form onSubmit={handleAddBookmark} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                  URL *
                </label>
                <input
                  type="url"
                  required
                  value={newUrl}
                  onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="https://example.com/article"
                  className="w-full px-3 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                  Title (Optional)
                </label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="Leave empty for auto-extraction"
                  className="w-full px-3 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                    Collection
                  </label>
                  <select
                    value={newCollectionId}
                    onChange={(e) => setNewCollectionId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)]"
                  >
                    <option value="">None (Uncategorized)</option>
                    {collections.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                    User Tags (comma separated)
                  </label>
                  <input
                    type="text"
                    value={newTagsStr}
                    onChange={(e) => setNewTagsStr(e.target.value)}
                    placeholder="research, ai, reads"
                    className="w-full px-3 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                  Personal Notes
                </label>
                <textarea
                  rows={2}
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  placeholder="Why did you bookmark this?"
                  className="w-full px-3 py-2 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)] resize-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface-hover)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAdd}
                  className="px-5 py-2 rounded-xl bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white text-sm font-semibold shadow-md transition"
                >
                  {submittingAdd ? "Saving..." : "Save Link"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Detail & Edit Drawer / Modal ────────────────────── */}
      {selectedBookmark && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="glass-card p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-fade-in shadow-2xl flex flex-col gap-6">
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-medium capitalize ${
                      selectedBookmark.status === "completed"
                        ? "bg-[var(--color-completed)]/20 text-[var(--color-completed)]"
                        : selectedBookmark.status === "processing"
                        ? "bg-[var(--color-processing)]/20 text-[var(--color-primary)] animate-pulse"
                        : selectedBookmark.status === "failed"
                        ? "bg-[var(--color-failed)]/20 text-[var(--color-failed)]"
                        : "bg-[var(--color-pending)]/20 text-[var(--color-pending)]"
                    }`}
                  >
                    {selectedBookmark.status}
                  </span>
                  {selectedBookmark.status === "failed" && (
                    <button
                      onClick={() => handleRetry(selectedBookmark.id)}
                      disabled={retryingId === selectedBookmark.id}
                      className="text-xs px-2 py-0.5 bg-[var(--color-failed)]/20 text-[var(--color-failed)] rounded hover:underline"
                    >
                      ↺ Retry Job
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  value={detailTitle}
                  onChange={(e) => setDetailTitle(e.target.value)}
                  placeholder="Bookmark Title"
                  className="text-xl font-bold bg-transparent border-b border-transparent hover:border-[var(--color-border)] focus:border-[var(--color-primary)] focus:outline-none w-full"
                />
                <a
                  href={selectedBookmark.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-[var(--color-accent)] hover:underline inline-flex items-center gap-1 mt-1 truncate max-w-lg"
                >
                  {selectedBookmark.url} ↗
                </a>
              </div>
              <button
                onClick={() => setSelectedBookmark(null)}
                className="text-xl text-[var(--color-text-muted)] hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Error Message if Failed */}
            {selectedBookmark.error_message && (
              <div className="p-3 rounded-lg bg-[var(--color-failed)]/10 border border-[var(--color-failed)]/30 text-[var(--color-failed)] text-xs">
                <strong>Error:</strong> {selectedBookmark.error_message}
              </div>
            )}

            {/* AI Summary (Editable) */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  🤖 AI Summary
                </label>
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  Editable for customization
                </span>
              </div>
              <textarea
                rows={4}
                value={detailSummary}
                onChange={(e) => setDetailSummary(e.target.value)}
                placeholder="AI summary will appear here once processed..."
                className="w-full p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)] resize-none"
              />
            </div>

            {/* Key Takeaways */}
            {selectedBookmark.key_takeaways && selectedBookmark.key_takeaways.length > 0 && (
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-2">
                  💡 Key Takeaways
                </label>
                <ul className="space-y-1.5 pl-4 list-disc text-xs text-[var(--color-text)]">
                  {selectedBookmark.key_takeaways.map((point, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Tags Management */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  🏷️ Tags
                </label>
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  Blue: AI • Green: User
                </span>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                {selectedBookmark.tags.map((bt) => (
                  <span
                    key={bt.tag.id}
                    className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border ${
                      bt.source === "ai"
                        ? "bg-[var(--color-primary)]/10 text-[var(--color-primary)] border-[var(--color-primary)]/30"
                        : "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/30"
                    }`}
                  >
                    #{bt.tag.name}
                    <button
                      onClick={() => handleRemoveTag(bt.tag.id)}
                      className="hover:font-bold ml-1 text-xs"
                      title="Remove tag"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>

              {/* Add Tag Form */}
              <form onSubmit={handleAddTagToDetail} className="flex gap-2 max-w-sm">
                <input
                  type="text"
                  value={newTagInput}
                  onChange={(e) => setNewTagInput(e.target.value)}
                  placeholder="Add a new tag..."
                  className="flex-1 px-3 py-1.5 text-xs rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] focus:outline-none focus:border-[var(--color-primary)]"
                />
                <button
                  type="submit"
                  className="px-3 py-1.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white text-xs font-medium rounded-lg"
                >
                  Add Tag
                </button>
              </form>
            </div>

            {/* Personal Notes */}
            <div>
              <label className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-2">
                📝 Personal Notes
              </label>
              <textarea
                rows={3}
                value={detailNotes}
                onChange={(e) => setDetailNotes(e.target.value)}
                placeholder="Add your own thoughts, references, or ideas..."
                className="w-full p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:border-[var(--color-primary)] resize-none"
              />
            </div>

            {/* Footer with Actions */}
            <div className="flex items-center justify-between border-t border-[var(--color-border)] pt-4 mt-2">
              <div className="flex gap-2">
                <button
                  onClick={() => handleToggleArchive(selectedBookmark)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
                >
                  {selectedBookmark.archived ? "Unarchive" : "Archive"}
                </button>
                <button
                  onClick={() => handleDeleteBookmark(selectedBookmark.id)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-[var(--color-danger)]/40 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10"
                >
                  Delete
                </button>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setSelectedBookmark(null)}
                  className="px-4 py-1.5 text-xs rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
                >
                  Close
                </button>
                <button
                  onClick={handleSaveDetail}
                  disabled={savingDetail}
                  className="px-5 py-1.5 text-xs bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white font-semibold rounded-lg shadow"
                >
                  {savingDetail ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
