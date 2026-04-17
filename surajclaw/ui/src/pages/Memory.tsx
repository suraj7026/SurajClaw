import { useState } from "react";

import { memoryApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { LogEntry } from "@/components/shared/LogEntry";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/cn";
import { formatNumber, formatRelative, truncate } from "@/lib/format";
import type { SimilarityHit, SimilarityResult } from "@/types/api";

type Target = "notes" | "entities" | "sessions";

const TARGETS: { id: Target; label: string; icon: string }[] = [
  { id: "notes", label: "Notes", icon: "description" },
  { id: "entities", label: "Entities", icon: "person" },
  { id: "sessions", label: "Sessions", icon: "forum" },
];

export default function Memory() {
  const { data: entities } = useApi(() => memoryApi.entities({ limit: 25 }), [], {
    pollMs: 30_000,
  });
  const { data: notes } = useApi(() => memoryApi.notes({ limit: 25 }), [], {
    pollMs: 30_000,
  });
  const { data: sessions } = useApi(
    () => memoryApi.sessionEmbeddings({ limit: 25 }),
    [],
    { pollMs: 30_000 },
  );

  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<Target>("notes");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [history, setHistory] = useState<
    { ts: string; target: Target; query: string; count: number }[]
  >([]);

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await memoryApi.search(query.trim(), target, 8);
      setResult(res);
      setHistory((h) =>
        [
          {
            ts: new Date().toISOString(),
            target,
            query: query.trim(),
            count: res.hits.length,
          },
          ...h,
        ].slice(0, 12),
      );
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "search failed";
      setSearchError(message);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Memory & Retrieval"
        subtitle="Vector store · entity graph · note index"
        icon="memory"
      />

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        <MetricCard
          label="Entities"
          value={formatNumber(entities?.count ?? 0)}
          icon="person"
          tone="primary"
          hint="People · Projects · Companies · Preferences"
        />
        <MetricCard
          label="Notes Indexed"
          value={formatNumber(notes?.count ?? 0)}
          icon="description"
          tone="tertiary"
          hint="Markdown notes with embeddings"
        />
        <MetricCard
          label="Session Embeddings"
          value={formatNumber(sessions?.count ?? 0)}
          icon="forum"
          tone="secondary"
          hint="Summaries indexed for recall"
        />
      </div>

      {/* Similarity search */}
      <Panel
        title="Similarity Search"
        icon="search"
        subtitle="pgvector cosine distance"
        className="mb-4"
        scanline
      >
        <form className="flex flex-col sm:flex-row gap-2" onSubmit={onSearch}>
          <div className="flex border border-border rounded">
            {TARGETS.map((t) => (
              <button
                type="button"
                key={t.id}
                onClick={() => setTarget(t.id)}
                className={cn(
                  "px-3 py-2 text-xs font-display uppercase tracking-wider",
                  "border-r border-border last:border-r-0",
                  target === t.id
                    ? "bg-primary/10 text-primary"
                    : "text-ink-dim hover:text-ink",
                )}
              >
                <span
                  className="material-symbols-outlined align-middle mr-1"
                  style={{ fontSize: "14px" }}
                >
                  {t.icon}
                </span>
                {t.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask the memory store…"
            className="input flex-1"
          />
          <button
            type="submit"
            disabled={searching || !query.trim()}
            className="btn-primary justify-center"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              {searching ? "hourglass_top" : "search"}
            </span>
            {searching ? "Searching…" : "Probe"}
          </button>
        </form>
        {searchError && (
          <p className="text-xs text-danger mt-3">{searchError}</p>
        )}
        {result && (
          <div className="mt-4">
            <p className="label-mono mb-2">
              Hits in {result.target} · {result.hits.length}
            </p>
            {result.hits.length === 0 ? (
              <EmptyState
                icon="filter_alt_off"
                title="No matches"
                description="Try a broader query or switch targets."
              />
            ) : (
              <ul className="space-y-2">
                {result.hits.map((h) => (
                  <SimilarityHitRow key={h.id} hit={h} />
                ))}
              </ul>
            )}
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Panel title="Entities" icon="person" bodyClassName="p-0">
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!entities || entities.results.length === 0 ? (
              <EmptyState icon="person_off" title="No entities" />
            ) : (
              <ul className="divide-y divide-border">
                {entities.results.map((e) => (
                  <li key={e.id} className="px-4 py-2.5 hover:bg-bg-raised/40">
                    <div className="flex items-center justify-between">
                      <span className="font-display text-sm">{e.name}</span>
                      <span className="label-mono text-primary">{e.entity_type}</span>
                    </div>
                    <p className="text-[11px] text-ink-dim mt-1 line-clamp-2 font-mono">
                      {Object.keys(e.attributes).length === 0
                        ? "(no attributes)"
                        : Object.entries(e.attributes)
                            .slice(0, 3)
                            .map(([k, v]) => `${k}=${String(v)}`)
                            .join(" · ")}
                    </p>
                    <p className="text-[10px] text-ink-mute mt-1">
                      {formatRelative(e.last_updated)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        <Panel title="Notes" icon="description" bodyClassName="p-0">
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!notes || notes.results.length === 0 ? (
              <EmptyState icon="note_alt" title="No notes" />
            ) : (
              <ul className="divide-y divide-border">
                {notes.results.map((n) => (
                  <li key={n.id} className="px-4 py-2.5 hover:bg-bg-raised/40">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-display text-sm truncate">{n.title}</span>
                      <span className="text-[10px] text-ink-mute font-mono shrink-0">
                        {formatRelative(n.updated_at)}
                      </span>
                    </div>
                    <p className="text-[10px] text-ink-mute font-mono truncate">
                      {n.filename}
                    </p>
                    {n.content_preview && (
                      <p className="text-[11px] text-ink-dim mt-1 line-clamp-2">
                        {n.content_preview}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        <Panel title="Session Embeddings" icon="forum" bodyClassName="p-0">
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!sessions || sessions.results.length === 0 ? (
              <EmptyState icon="chat" title="No summaries" />
            ) : (
              <ul className="divide-y divide-border">
                {sessions.results.map((s) => (
                  <li key={s.id} className="px-4 py-2.5 hover:bg-bg-raised/40">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-primary truncate">
                        {s.session.slice(0, 8)}…
                      </span>
                      <span className="text-[10px] text-ink-mute font-mono">
                        {formatRelative(s.created_at)}
                      </span>
                    </div>
                    <p className="text-[11px] text-ink-dim mt-1 line-clamp-3">
                      {s.summary_text || "(empty summary)"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>

      {/* Retrieval log */}
      <Panel title="Retrieval Log" icon="history" className="mt-4" bodyClassName="p-0">
        {history.length === 0 ? (
          <EmptyState
            icon="hourglass_empty"
            title="No probes yet"
            description="Search history will accumulate here for the session."
          />
        ) : (
          <ul className="divide-y divide-border">
            {history.map((h, i) => (
              <li key={i} className="px-4 py-2">
                <LogEntry
                  timestamp={h.ts}
                  tag={`PROBE·${h.target.toUpperCase()}`}
                  message={`${h.query} — ${h.count} hit${h.count === 1 ? "" : "s"}`}
                  tone="primary"
                />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function SimilarityHitRow({ hit }: { hit: SimilarityHit }) {
  const score = Math.max(0, 1 - hit.distance);
  return (
    <li className="border border-border rounded-md p-3 bg-bg-base/40 hover:border-primary/40 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="label-mono text-primary">{hit.kind}</span>
            <span className="font-display text-sm truncate">{hit.title}</span>
          </div>
          <p className="text-[11px] text-ink-dim line-clamp-2">
            {truncate(hit.snippet, 220)}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-mono text-xs text-primary">{score.toFixed(3)}</p>
          <p className="label-mono">SIM</p>
        </div>
      </div>
    </li>
  );
}
