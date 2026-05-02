import { useState } from "react";

import { memoryApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
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
  { id: "entities", label: "Entities", icon: "database" },
  { id: "sessions", label: "Sessions", icon: "bubble_chart" },
];

export default function Memory() {
  const { data: entities } = useApi(() => memoryApi.entities({ limit: 25 }), [], { pollMs: 30_000 });
  const { data: notes } = useApi(() => memoryApi.notes({ limit: 25 }), [], { pollMs: 30_000 });
  const { data: sessions } = useApi(() => memoryApi.sessionEmbeddings({ limit: 25 }), [], { pollMs: 30_000 });

  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<Target>("notes");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [history, setHistory] = useState<{ ts: string; target: Target; query: string; count: number }[]>([]);

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await memoryApi.search(query.trim(), target, 8);
      setResult(res);
      setHistory((h) =>
        [{ ts: new Date().toISOString(), target, query: query.trim(), count: res.hits.length }, ...h].slice(0, 12),
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "search failed";
      setSearchError(message);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="SURAJCLAW | Memory & Retrieval"
        subtitle="Manage semantic storage, browse notes, and run vector similarity checks."
        icon="memory"
      />

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        <MetricCard label="Entities" value={formatNumber(entities?.count ?? 0)} icon="database" tone="primary" hint="People · Projects · Preferences" />
        <MetricCard label="Notes Indexed" value={formatNumber(notes?.count ?? 0)} icon="description" tone="tertiary" hint="Markdown notes with embeddings" />
        <MetricCard label="Session Embeddings" value={formatNumber(sessions?.count ?? 0)} icon="bubble_chart" tone="secondary" hint="Summaries indexed for recall" />
      </div>

      {/* Similarity Search Tool */}
      <Panel title="Similarity Search Tool" icon="manage_search" className="mb-6" scanline>
        <form className="flex flex-col sm:flex-row gap-3" onSubmit={onSearch}>
          <div className="flex border border-border rounded overflow-hidden">
            {TARGETS.map((t) => (
              <button
                type="button"
                key={t.id}
                onClick={() => setTarget(t.id)}
                className={cn(
                  "px-3 py-2 text-xs font-display uppercase tracking-wider border-r border-border last:border-r-0",
                  target === t.id ? "bg-primary/10 text-primary" : "text-ink-dim hover:text-ink",
                )}
              >
                <span className="material-symbols-outlined align-middle mr-1" style={{ fontSize: "14px" }}>{t.icon}</span>
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex-1 relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 font-display text-primary text-xs">SURAJCLAW &gt;</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for recent session context..."
              className="input w-full pl-28"
            />
          </div>
          <button type="submit" disabled={searching || !query.trim()} className="btn-solid">
            {searching ? "Searching..." : "Execute Vec Query"}
          </button>
        </form>
        {searchError && <p className="text-xs text-danger mt-3">{searchError}</p>}
        {result && (
          <div className="mt-4">
            <p className="label-mono mb-2">Hits in {result.target} · {result.hits.length}</p>
            {result.hits.length === 0 ? (
              <EmptyState icon="filter_alt_off" title="No matches" description="Try a broader query or switch targets." />
            ) : (
              <ul className="space-y-2">
                {result.hits.map((h) => <SimilarityHitRow key={h.id} hit={h} />)}
              </ul>
            )}
          </div>
        )}
      </Panel>

      {/* Memory domains grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Panel title="Entity (Facts)" icon="database" bodyClassName="p-0">
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!entities || entities.results.length === 0 ? (
              <EmptyState icon="person_off" title="No entities" />
            ) : (
              <div className="space-y-3 p-4">
                {entities.results.map((e) => (
                  <div key={e.id} className="p-4 bg-bg-raised rounded-lg hover:bg-bg-overlay transition-colors cursor-pointer">
                    <div className="flex justify-between mb-2">
                      <span className="font-display text-xs font-bold text-secondary">{e.entity_type}</span>
                      <span className="text-[9px] text-ink-mute font-display">{formatRelative(e.last_updated)}</span>
                    </div>
                    <p className="text-sm">{e.name}</p>
                    <p className="text-[11px] text-ink-dim mt-1 line-clamp-2 font-mono">
                      {Object.keys(e.attributes).length === 0
                        ? "(no attributes)"
                        : Object.entries(e.attributes).slice(0, 3).map(([k, v]) => `${k}=${String(v)}`).join(" · ")}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="NoteIndex (Markdown)" icon="description" bodyClassName="p-0">
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!notes || notes.results.length === 0 ? (
              <EmptyState icon="note_alt" title="No notes" />
            ) : (
              <div className="space-y-2 p-4">
                {notes.results.map((n) => (
                  <div key={n.id} className="group">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="material-symbols-outlined text-primary" style={{ fontSize: "16px" }}>sticky_note_2</span>
                      <span className="font-display text-xs font-semibold group-hover:text-primary transition-colors cursor-pointer">
                        {n.title}
                      </span>
                    </div>
                    <div className="bg-bg-lowest p-3 rounded-sm border-l-2 border-primary/40">
                      <p className="text-[11px] text-ink-dim line-clamp-3">{n.content_preview || n.filename}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="SessionEmbeddings" icon="bubble_chart" bodyClassName="p-0"
          actions={<StatusIndicator status="info" label="Realtime" />}
        >
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {!sessions || sessions.results.length === 0 ? (
              <EmptyState icon="chat" title="No summaries" />
            ) : (
              <div className="space-y-3 p-4">
                {sessions.results.map((s) => (
                  <div key={s.id} className="flex items-start gap-3 p-2 border-l border-tertiary/30">
                    <div className="w-1.5 h-1.5 rounded-full bg-tertiary mt-1.5 shrink-0" />
                    <div className="flex-1">
                      <div className="flex justify-between">
                        <span className="font-display text-[10px] font-bold uppercase">{s.session.slice(0, 8)}...</span>
                        <span className="font-display text-[10px] text-ink-mute">{formatRelative(s.created_at)}</span>
                      </div>
                      <p className="text-[11px] text-ink-dim mt-1 italic line-clamp-2">{s.summary_text || "(empty summary)"}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Retrieval log */}
      <Panel title="Retrieval Log Stream" icon="history" className="mt-6" bodyClassName="p-0">
        {history.length === 0 ? (
          <EmptyState icon="hourglass_empty" title="No probes yet" description="Search history will accumulate here." />
        ) : (
          <div className="bg-bg-lowest p-4 font-mono text-xs space-y-1">
            {history.map((h, i) => (
              <LogEntry key={i} timestamp={h.ts} tag={`PROBE·${h.target.toUpperCase()}`}
                message={`${h.query} — ${h.count} hit${h.count === 1 ? "" : "s"}`} tone="primary"
              />
            ))}
            <div className="flex items-center gap-2 text-primary mt-2">
              <span>SURAJCLAW &gt;</span>
              <span className="w-2 h-4 bg-primary animate-pulse" />
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function SimilarityHitRow({ hit }: { hit: SimilarityHit }) {
  const score = Math.max(0, 1 - hit.distance);
  return (
    <li className="border border-border rounded-md p-3 bg-bg-raised hover:border-primary/40 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="label-mono text-primary">{hit.kind}</span>
            <span className="font-display text-sm truncate">{hit.title}</span>
          </div>
          <p className="text-[11px] text-ink-dim line-clamp-2">{truncate(hit.snippet, 220)}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-mono text-xs text-primary">{score.toFixed(3)}</p>
          <p className="label-mono">SIM</p>
        </div>
      </div>
    </li>
  );
}
