"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function EpisodePage() {
  const router = useRouter();
  useEffect(() => { router.replace("/"); }, [router]);
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-zinc-950 via-zinc-900 to-zinc-950">
      <span className="text-zinc-500 text-sm">Redirecting…</span>
    </div>
  );
}
