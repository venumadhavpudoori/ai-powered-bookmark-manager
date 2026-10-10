"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/api";
import Link from "next/link";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated()) {
      router.push("/dashboard");
    }
  }, [router]);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      {/* Background gradient */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0a0a0f] via-[#12121a] to-[#0a0a0f]" />
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#7c5cfc] rounded-full opacity-10 blur-[120px]" />
        <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[400px] bg-[#00d4aa] rounded-full opacity-8 blur-[100px]" />
      </div>

      {/* Logo & tagline */}
      <div className="text-center animate-fade-in mb-12">
        <h1 className="text-6xl font-bold mb-4">
          <span className="gradient-text">RecallAI</span>
        </h1>
        <p className="text-xl text-[var(--color-text-muted)] max-w-md mx-auto leading-relaxed">
          Save a link. Extract insights. Find it later by{" "}
          <span className="text-[var(--color-accent)]">meaning</span>.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mb-12 animate-slide-up">
        <div className="glass-card p-6 text-center">
          <div className="text-3xl mb-3">🔗</div>
          <h3 className="font-semibold text-lg mb-2">Save</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Bookmark any URL with one click
          </p>
        </div>
        <div className="glass-card p-6 text-center">
          <div className="text-3xl mb-3">🤖</div>
          <h3 className="font-semibold text-lg mb-2">Enrich</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            AI summarizes, tags, and extracts key takeaways
          </p>
        </div>
        <div className="glass-card p-6 text-center">
          <div className="text-3xl mb-3">🔍</div>
          <h3 className="font-semibold text-lg mb-2">Recall</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Semantic search finds bookmarks by meaning
          </p>
        </div>
      </div>

      {/* CTA buttons */}
      <div className="flex gap-4 animate-slide-up">
        <Link
          href="/register"
          className="px-8 py-3 rounded-xl font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white shadow-lg shadow-[var(--color-primary)]/25 hover:shadow-[var(--color-primary)]/40 hover:-translate-y-0.5"
        >
          Get Started
        </Link>
        <Link
          href="/login"
          className="px-8 py-3 rounded-xl font-semibold border border-[var(--color-border)] hover:border-[var(--color-text-muted)] hover:-translate-y-0.5"
        >
          Sign In
        </Link>
      </div>
    </main>
  );
}
