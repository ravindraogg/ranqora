'use client';

import { useState, useEffect, useMemo, useRef, Suspense } from 'react';
import {
    Hexagon, ArrowLeft, Search, Loader2, ExternalLink,
    Download, Heart, Tag, Calendar, BarChart2, X, ChevronRight,
    Database, Globe, FileText, Brain, Zap, Shield, AlertTriangle
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSearchParams } from 'next/navigation';

// ─── Types matching backend schemas ─────────────────────────────────────────

interface RankingBreakdown { semantic?: number; task?: number; quality?: number; license?: number; freshness?: number; graph?: number; }
interface Explanation { why_relevant?: string; license_note?: string; tradeoff?: string; confidence?: string; }
interface DatasetMetadata {
    id: string; source: string; description: string; downloads: number; likes: number;
    url: string; license: string; last_modified: string; tags: string[];
    similarity_score: number; ranking_breakdown?: RankingBreakdown;
    explanation?: Explanation;
}
interface DatasetPreview {
    type: string; columns?: string[]; rows?: Record<string, string | null>[];
    image_urls?: string[]; text_samples?: string[]; file_structure?: string[];
}
interface DatasetDetailResponse {
    metadata?: DatasetMetadata; preview?: DatasetPreview; redirect_url: string;
    estimated_download_time?: string; size_bytes?: number; size_readable?: string;
}
interface GoalPlan {
    objective?: string;
    constraints?: { domain?: string; tasks?: string[]; preferred_licenses?: string[]; annotation_requirements?: string[] };
    success_criteria?: Record<string, unknown>;
    search_strategy?: { primary_query?: string; keyword_variants?: string[]; tool_priority?: string[]; approach?: string };
    uncertainty_note?: string;
}
interface Uncertainty {
    overall?: string;
    confidence?: number;
    quality_label?: string;
    known_gaps?: string[];
    suggestion?: string;
}
interface AgentReport {
    goal_plan?: GoalPlan;
    evaluation?: { confidence?: number; quality_label?: string; summary?: string; should_expand?: boolean; self_adjustment?: string[] };
    uncertainty?: Uncertainty;
}
interface AgentPerception {
    domain?: string;
    modality?: string;
    primary_tasks?: string[];
    secondary_tasks?: string[];
    constraints?: { required_annotations?: string[]; preferred_format?: string; min_quality?: string };
    uncertainty_level?: string;
    strategy_reasoning?: string;
    tool_rationale?: string;
    risk_notes?: string[];
}

// SESSION_KEY is just the localStorage slot name.
// The VALUE stored at this key is always the real client_id returned by GET /api/auth/client_id
const SESSION_KEY = 'ranqora_client_id';
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

// These labels match exactly what the backend emits — they get overwritten
// live with the actual text sent from the server.
const INITIAL_STAGES = [
    "Parsing query with Gemini LLM...",
    "Querying Kaggle, HuggingFace, OpenData, ArXiv, GitHub...",
    "Ingesting candidates into knowledge graph...",
    "Running LightGBM LambdaRank relevance scoring...",
    "Preparing final ranked results...",
];
const TOTAL_STAGES = INITIAL_STAGES.length;

// ─── Source Badge ────────────────────────────────────────────────────────────
function SourceBadge({ source }: { source: string }) {
    const map: Record<string, { bg: string; label: string }> = {
        huggingface: { bg: 'bg-yellow-50 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20', label: 'HuggingFace' },
        kaggle: { bg: 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20', label: 'Kaggle' },
        intranet: { bg: 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20', label: 'Intranet' },
    };
    const style = map[source.toLowerCase()] ?? { bg: 'bg-gray-50 dark:bg-white/5 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-white/10', label: source };
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${style.bg}`}>{style.label}</span>;
}

// ─── Dataset Card ────────────────────────────────────────────────────────────
function DatasetCard({ ds, onClick, isSelected }: { ds: DatasetMetadata; onClick: () => void; isSelected?: boolean }) {
    const score = Math.round(ds.similarity_score * 100);
    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -2 }}
            className={`group relative bg-white dark:bg-[#111113] border rounded-3xl p-5 flex flex-col justify-between shadow-sm hover:shadow-md transition-all cursor-pointer ${isSelected
                ? 'border-indigo-500 dark:border-indigo-500/60 ring-2 ring-indigo-500/20'
                : 'border-gray-200 dark:border-white/5 hover:border-indigo-300 dark:hover:border-indigo-500/40'
                }`}
            onClick={onClick}
        >
            {/* Header */}
            <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 flex items-center justify-center shrink-0">
                    <Database className="w-5 h-5 text-indigo-500" />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[200px]">{ds.id}</h3>
                        <SourceBadge source={ds.source} />
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 leading-relaxed">{ds.description}</p>
                </div>
                {/* Score chip */}
                <div className="shrink-0 flex flex-col items-end">
                    <div className="text-[10px] text-gray-400 mb-0.5">match</div>
                    <div className={`text-sm font-black ${score >= 70 ? 'text-green-500' : score >= 40 ? 'text-amber-500' : 'text-gray-400'}`}>{score}%</div>
                </div>
            </div>

            {/* Tags */}
            {ds.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-3">
                    {ds.tags.slice(0, 4).map((t, i) => (
                        <span key={`${i}-${t}`} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-500 border border-gray-200 dark:border-white/10">{t}</span>
                    ))}
                    {ds.tags.length > 4 && <span className="text-[10px] text-gray-400">+{ds.tags.length - 4}</span>}
                </div>
            )}

            {/* Agent Explanation */}
            {ds.explanation && (
                <div className="mt-4 bg-gray-50/50 dark:bg-white/3 border border-gray-100 dark:border-white/5 rounded-2xl p-3 space-y-2">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                        Agent Notes
                    </p>
                    {ds.explanation.why_relevant && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed"><span className="font-semibold text-gray-700 dark:text-gray-300">Relevance:</span> {ds.explanation.why_relevant}</p>
                    )}
                    {ds.explanation.tradeoff && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 leading-relaxed italic">{ds.explanation.tradeoff}</p>
                    )}
                </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100 dark:border-white/5">
                <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-500">
                    <span className="flex items-center gap-1"><Download className="w-3 h-3" />{ds.downloads.toLocaleString()}</span>
                    <span className="flex items-center gap-1"><Heart className="w-3 h-3" />{ds.likes.toLocaleString()}</span>
                    {ds.license !== 'unknown' && <span className="flex items-center gap-1"><FileText className="w-3 h-3" />{ds.license}</span>}
                </div>
                <span className="text-xs text-indigo-500 dark:text-indigo-400 group-hover:underline flex items-center gap-1">
                    Preview <ChevronRight className="w-3 h-3" />
                </span>
            </div>
        </motion.div>
    );
}

// ─── Inline Dataset Detail Panel (Mac editor style) ──────────────────────────
function DatasetDetailPanel({ ds, onBack }: { ds: DatasetMetadata; onBack: () => void }) {
    const [detail, setDetail] = useState<DatasetDetailResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showAllRows, setShowAllRows] = useState(false);

    useEffect(() => {
        setLoading(true);
        setError(null);
        setDetail(null);
        setShowAllRows(false);
        async function load() {
            try {
                const res = await fetch(`${API_BASE}/api/projects/dataset/${ds.source}/${ds.id}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                setDetail(await res.json());
            } catch (e: unknown) {
                setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }
        load();
    }, [ds]);

    const preview = detail?.preview;
    const displayRows = preview?.rows
        ? (showAllRows ? preview.rows : preview.rows.slice(0, 5))
        : [];

    return (
        <motion.div
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="flex flex-col h-full"
        >


            {/* Detail content */}
            <div className="flex-1 overflow-y-auto">
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-64 gap-4">
                        <div className="relative w-10 h-10">
                            <div className="absolute inset-0 border-2 border-gray-100 dark:border-white/5 rounded-full"></div>
                            <div className="absolute inset-0 border-2 border-indigo-500 rounded-full border-t-transparent animate-spin"></div>
                        </div>
                        <p className="text-sm text-gray-400">Fetching dataset details...</p>
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center h-64 gap-3">
                        <p className="text-sm text-red-500">Failed to load details: {error}</p>
                        <p className="text-xs text-gray-400">Using available metadata instead.</p>
                    </div>
                ) : (
                    <div className="p-6 space-y-6">
                        {/* Dataset header info */}
                        <div className="flex items-start gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 flex items-center justify-center shrink-0">
                                <Database className="w-6 h-6 text-indigo-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h2 className="text-lg font-bold text-gray-900 dark:text-white">{ds.id}</h2>
                                    <SourceBadge source={ds.source} />
                                </div>
                                <p className="text-xs text-gray-400 mt-1">
                                    Match: <span className="text-indigo-500 font-semibold">{Math.round(ds.similarity_score * 100)}%</span>
                                    {detail?.size_readable && <> · {detail.size_readable}</>}
                                    {detail?.estimated_download_time && <> · ~{detail.estimated_download_time}</>}
                                </p>
                            </div>
                        </div>

                        {/* Description */}
                        <div className="bg-gray-50/50 dark:bg-white/[0.02] rounded-2xl border border-gray-100 dark:border-white/5 p-4">
                            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Description</h4>
                            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{detail?.metadata?.description || ds.description}</p>
                        </div>

                        {/* Meta grid */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            {[
                                { icon: Download, label: 'Downloads', value: ds.downloads.toLocaleString() },
                                { icon: Heart, label: 'Likes', value: ds.likes.toLocaleString() },
                                { icon: FileText, label: 'License', value: ds.license },
                                { icon: Calendar, label: 'Last Modified', value: ds.last_modified ? new Date(ds.last_modified).toLocaleDateString() : 'N/A' },
                            ].map(({ icon: Icon, label, value }) => (
                                <div key={label} className="bg-gray-50 dark:bg-white/5 rounded-2xl p-3 border border-gray-200 dark:border-white/5">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Icon className="w-3.5 h-3.5 text-gray-400" />
                                        <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">{label}</span>
                                    </div>
                                    <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{value || '—'}</p>
                                </div>
                            ))}
                        </div>

                        {/* Ranking breakdown */}
                        {ds.ranking_breakdown && (
                            <div className="bg-gray-50/50 dark:bg-white/[0.02] rounded-2xl border border-gray-100 dark:border-white/5 p-4">
                                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                                    <BarChart2 className="w-3.5 h-3.5" /> Ranking Breakdown
                                </h4>
                                <div className="space-y-2">
                                    {Object.entries(ds.ranking_breakdown).map(([key, val]) => (
                                        <div key={key} className="flex items-center gap-3">
                                            <span className="text-xs text-gray-500 w-20 capitalize">{key}</span>
                                            <div className="flex-1 h-2 bg-gray-100 dark:bg-white/5 rounded-full overflow-hidden">
                                                <motion.div
                                                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
                                                    initial={{ width: 0 }}
                                                    animate={{ width: `${Math.round((val as number) * 100)}%` }}
                                                    transition={{ duration: 0.6, ease: 'easeOut' }}
                                                />
                                            </div>
                                            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 w-10 text-right">{Math.round((val as number) * 100)}%</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Tags */}
                        {ds.tags.length > 0 && (
                            <div>
                                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-2"><Tag className="w-3.5 h-3.5" /> Tags</h4>
                                <div className="flex flex-wrap gap-2">
                                    {ds.tags.map(t => (
                                        <span key={t} className="text-xs px-3 py-1 rounded-full bg-gray-100 dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-400">{t}</span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Data Preview — tabular */}
                        {preview?.type === 'tabular' && preview.columns && preview.columns.length > 0 && preview.rows && (
                            <div>
                                <div className="flex items-center justify-between mb-3">
                                    <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                        <Database className="w-3.5 h-3.5" /> Data Preview
                                        <span className="text-gray-300 dark:text-gray-700">({displayRows.length}/{preview.rows.length} rows)</span>
                                    </h4>
                                    {preview.rows.length > 5 && (
                                        <button onClick={() => setShowAllRows(v => !v)} className="text-xs text-indigo-500 hover:underline">
                                            {showAllRows ? 'Show less' : `Show all ${preview.rows.length} rows`}
                                        </button>
                                    )}
                                </div>
                                <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-white/5">
                                    <table className="min-w-full text-xs">
                                        <thead className="bg-gray-50 dark:bg-white/5">
                                            <tr>
                                                {preview.columns.map(col => (
                                                    <th key={col} className="px-4 py-2.5 text-left text-gray-500 dark:text-gray-400 font-semibold whitespace-nowrap border-b border-gray-200 dark:border-white/5">{col}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {displayRows.map((row, i) => (
                                                <tr key={i} className={i % 2 === 0 ? 'bg-white dark:bg-transparent' : 'bg-gray-50/50 dark:bg-white/[0.02]'}>
                                                    {preview.columns!.map(col => (
                                                        <td key={col} className="px-4 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[200px] truncate">
                                                            {row[col] ?? <span className="text-gray-300 dark:text-gray-700 italic">null</span>}
                                                        </td>
                                                    ))}
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Text samples */}
                        {preview?.type === 'nlp' && preview.text_samples && preview.text_samples.length > 0 && (
                            <div>
                                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2"><FileText className="w-3.5 h-3.5" /> Text Samples</h4>
                                <div className="space-y-2">
                                    {preview.text_samples.slice(0, 5).map((s, i) => (
                                        <div key={i} className="bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/5 rounded-2xl px-4 py-3 text-xs text-gray-700 dark:text-gray-300 leading-relaxed">
                                            {s}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Image previews */}
                        {preview?.type === 'image' && preview.image_urls && (
                            <div>
                                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Image Samples</h4>
                                <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                                    {preview.image_urls.slice(0, 10).map((url, i) => (
                                        <img key={i} src={url} alt={`sample-${i}`} className="rounded-2xl object-cover aspect-square border border-gray-200 dark:border-white/5 bg-gray-100 dark:bg-white/5" />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* File structure */}
                        {preview?.file_structure && (
                            <div>
                                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2 flex items-center gap-2"><Globe className="w-3.5 h-3.5" /> File Structure</h4>
                                <div className="bg-gray-50 dark:bg-[#0c0c0e] rounded-2xl border border-gray-200 dark:border-white/5 p-4 font-mono text-xs text-gray-600 dark:text-gray-400 space-y-1">
                                    {preview.file_structure.map((f, i) => (
                                        <div key={i}>{f}</div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Footer with external link */}
            <div className="flex items-center justify-between p-4 border-t border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-[#111113] rounded-b-3xl shrink-0">
                <button
                    onClick={onBack}
                    className="flex items-center gap-2 px-4 py-2 rounded-2xl text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back
                </button>
                <a
                    href={detail?.redirect_url || ds.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 px-6 py-2.5 rounded-2xl text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 via-purple-600 to-blue-600 hover:opacity-90 transition-all shadow-lg shadow-indigo-500/20"
                >
                    <ExternalLink className="w-4 h-4" />
                    Open Dataset
                </a>
            </div>
        </motion.div>
    );
}



// ─── Main Page ────────────────────────────────────────────────────────────────
function SearchResultsContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const query = searchParams.get('q') || '';
    const clientIdFromUrl = searchParams.get('cid');

    const [currentStageIndex, setCurrentStageIndex] = useState(0);
    const [stageLabels, setStageLabels] = useState<string[]>(INITIAL_STAGES);
    const [isLoading, setIsLoading] = useState(true);
    const [datasets, setDatasets] = useState<DatasetMetadata[]>([]);
    const [apiError, setApiError] = useState<string | null>(null);
    const [selectedDataset, setSelectedDataset] = useState<DatasetMetadata | null>(null);
    const [status, setStatus] = useState<string>('');
    const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
    const [clientId, setClientId] = useState<string | null>(null);
    const [goalPlan, setGoalPlan] = useState<GoalPlan | null>(null);
    const [agentReport, setAgentReport] = useState<AgentReport | null>(null);
    const [filterText, setFilterText] = useState('');
    const [agentPerception, setAgentPerception] = useState<AgentPerception | null>(null);

    // ── Live elapsed timer ──────────────────────────────────────────────
    const timerStartRef = useRef<number>(Date.now());
    const [elapsedMs, setElapsedMs] = useState(0);

    useEffect(() => {
        if (!isLoading) return;
        timerStartRef.current = Date.now();
        const interval = setInterval(() => {
            setElapsedMs(Date.now() - timerStartRef.current);
        }, 100);
        return () => clearInterval(interval);
    }, [isLoading]);

    const elapsedDisplay = (elapsedMs / 1000).toFixed(1);

    // Derive unique sources for filter pills
    const availableSources = useMemo(() => {
        const sources = new Set(datasets.map(d => d.source.toLowerCase()));
        return Array.from(sources);
    }, [datasets]);

    // Filter datasets by platform/source name using the search bar
    const filteredDatasets = useMemo(() => {
        const term = filterText.trim().toLowerCase();
        if (!term) return datasets;
        return datasets.filter(ds =>
            ds.source.toLowerCase().includes(term) ||
            ds.id.toLowerCase().includes(term)
        );
    }, [datasets, filterText]);

    // Step 1: Validate client_id — redirect to /search if missing
    useEffect(() => {
        const stored = typeof window !== 'undefined' ? sessionStorage.getItem(SESSION_KEY) : null;
        const resolved = clientIdFromUrl || stored;
        if (!resolved) {
            router.replace('/search');
            return;
        }
        setClientId(resolved);
    }, [clientIdFromUrl, router]);

    // Step 2: Open SSE stream once clientId is available
    useEffect(() => {
        if (!clientId) return;

        let cancelled = false;

        async function stream() {
            try {
                const res = await fetch(`${API_BASE}/api/projects/rank/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, client_id: clientId }),
                });

                if (res.status === 403) { router.replace('/search'); return; }
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                if (!res.body) throw new Error('No response body');

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (!cancelled) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });

                    // SSE events are separated by \n\n
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop() ?? ''; // last incomplete chunk goes back to buffer

                    for (const part of parts) {
                        const line = part.trim();
                        if (!line.startsWith('data: ')) continue;
                        const raw = line.slice(6);
                        let evt: Record<string, unknown>;
                        try { evt = JSON.parse(raw); } catch { continue; }

                        // Auth / generic error from backend
                        if (evt.error) {
                            if ((evt.status_code as number) === 403) {
                                router.replace('/search');
                                return;
                            }
                            setApiError(evt.error as string);
                            setIsLoading(false);
                            setCurrentStageIndex(TOTAL_STAGES);
                            return;
                        }

                        // Stage advancement — backend tells us which step just began
                        if (typeof evt.stage === 'number') {
                            const idx = evt.stage as number;
                            setCurrentStageIndex(idx + 1); // show it as "in progress"
                            if (typeof evt.text === 'string') {
                                setStageLabels(prev => {
                                    const next = [...prev];
                                    next[idx] = evt.text as string;
                                    return next;
                                });
                            }
                        }

                        // Per-source result count (emitted after retrieval)
                        if (typeof evt.source === 'string' && typeof evt.count === 'number') {
                            setSourceCounts(prev => ({ ...prev, [evt.source as string]: evt.count as number }));
                        }

                        // Agent perception (visible reasoning trace)
                        if (evt.agent_perception) {
                            setAgentPerception(evt.agent_perception as AgentPerception);
                        }

                        // Goal plan emitted right after LLM stage
                        if (evt.goal_plan) {
                            setGoalPlan(evt.goal_plan as GoalPlan);
                        }

                        // Final done payload
                        if (evt.done) {
                            setDatasets((evt.datasets as DatasetMetadata[]) || []);
                            setStatus((evt.status as string) || 'Done');
                            setSourceCounts(prev => ({ ...prev, ...((evt.source_counts as Record<string, number>) || {}) }));
                            if (evt.agent_report) setAgentReport(evt.agent_report as AgentReport);
                            setCurrentStageIndex(TOTAL_STAGES);
                            setIsLoading(false);
                        }
                    }
                }
            } catch (e: unknown) {
                if (!cancelled) {
                    setApiError((e as Error).message);
                    setIsLoading(false);
                    setCurrentStageIndex(TOTAL_STAGES);
                }
            }
        }

        stream();
        return () => { cancelled = true; };
    }, [clientId, query, router]);

    return (
        <div className="h-screen w-screen bg-black p-2 md:p-3 overflow-hidden flex flex-col">
            <div className="flex-1 bg-[#FAFAFA] dark:bg-[#0c0c0e] rounded-2xl md:rounded-3xl border border-gray-200 dark:border-white/10 flex flex-col overflow-hidden shadow-2xl">

                {/* Header */}
                <div className="flex h-16 border-b border-gray-100 dark:border-white/5 bg-white dark:bg-[#111113] rounded-t-2xl md:rounded-t-3xl items-center px-4 xl:px-6 justify-between shrink-0">
                    <div className="flex items-center gap-2 md:gap-4">
                        {/* Mac-style window controls */}
                        <div className="hidden sm:flex flex-row gap-2 items-center mr-2">
                            <div className="w-3.5 h-3.5 rounded-full bg-[#FF5F56] border border-[#E0443E]"></div>
                            <div className="w-3.5 h-3.5 rounded-full bg-[#FFBD2E] border border-[#DEA123]"></div>
                            <div className="w-3.5 h-3.5 rounded-full bg-[#27C93F] border border-[#1AAB29]"></div>
                        </div>
                        <Link href="/search" className="flex items-center gap-2 px-3 py-1.5 md:px-4 md:py-2 rounded-full bg-gray-50 dark:bg-white/5 hover:bg-gray-100 dark:hover:bg-white/10 text-gray-700 dark:text-gray-300 transition-colors">
                            <ArrowLeft className="w-4 h-4 md:w-5 md:h-5" />
                            <span className="text-xs md:text-sm font-semibold hidden sm:inline">Go Back</span>
                        </Link>
                    </div>
                    <div className="absolute left-1/2 -translate-x-1/2 hidden md:flex h-9 w-96 items-center justify-center rounded-full bg-gray-50 dark:bg-black border border-gray-200 dark:border-white/10 text-sm font-mono text-gray-500 shadow-inner">
                        ranqora / search / results
                    </div>
                    <div className="flex items-center gap-3">
                        {/* Timer */}
                        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono tabular-nums transition-all ${isLoading
                            ? 'bg-indigo-500/10 text-indigo-500 border border-indigo-500/20'
                            : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                            }`}>
                            {isLoading ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            )}
                            {elapsedDisplay}s
                        </div>
                        <div className="hidden sm:flex items-center gap-2 opacity-70">
                            <Hexagon className="w-4 h-4 text-indigo-500" />
                            <span className="text-xs font-bold text-gray-900 dark:text-white tracking-wider uppercase">Ranqora</span>
                        </div>
                    </div>
                </div>

                {/* Body */}
                <div className="flex-1 flex overflow-hidden">

                    {/* LEFT SIDEBAR */}
                    <div className="w-72 border-r border-gray-200 dark:border-white/5 shrink-0 hidden md:flex flex-col p-5 gap-6 overflow-y-auto">
                        <AnimatePresence mode="wait">
                            {isLoading ? (
                                <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col gap-5">
                                    <div className="flex items-center gap-3 pb-4 border-b border-gray-100 dark:border-white/5">
                                        <div className="relative w-8 h-8 shrink-0">
                                            <div className="absolute inset-0 border-2 border-gray-100 dark:border-white/5 rounded-full"></div>
                                            <div className="absolute inset-0 border-2 border-indigo-500 rounded-full border-t-transparent animate-spin"></div>
                                            <Hexagon className="absolute inset-0 m-auto w-3.5 h-3.5 text-indigo-500" />
                                        </div>
                                        <div className="min-w-0">
                                            <p className="text-sm font-semibold text-gray-900 dark:text-white">Processing</p>
                                            <p className="text-xs text-gray-400 truncate">&quot;{query}&quot;</p>
                                        </div>
                                    </div>
                                    <div className="space-y-3">
                                        {stageLabels.map((label, idx) => {
                                            const isPast = idx < currentStageIndex - 1;
                                            const isCurrent = idx === currentStageIndex - 1;
                                            return (
                                                <motion.div key={idx} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.04 }}
                                                    className={`flex items-start gap-2.5 text-xs transition-all duration-300 ${isPast ? 'text-gray-400 dark:text-gray-600' : isCurrent ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : 'text-gray-300 dark:text-gray-700'}`}
                                                >
                                                    <div className="w-4 h-4 flex-none flex items-center justify-center mt-0.5">
                                                        {isPast && <div className="w-2 h-2 rounded-full bg-green-500"></div>}
                                                        {isCurrent && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                                        {!isPast && !isCurrent && <div className="w-2 h-2 rounded-full border border-current opacity-40"></div>}
                                                    </div>
                                                    <span className="leading-snug">{label}</span>
                                                </motion.div>
                                            );
                                        })}
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-[11px] text-gray-400 dark:text-gray-600 mb-1.5">
                                            <span>Progress</span>
                                            <span>{Math.round((currentStageIndex / TOTAL_STAGES) * 100)}%</span>
                                        </div>
                                        <div className="h-1 bg-gray-100 dark:bg-white/5 rounded-full overflow-hidden">
                                            <motion.div className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-blue-500 rounded-full"
                                                initial={{ width: '0%' }}
                                                animate={{ width: `${(currentStageIndex / TOTAL_STAGES) * 100}%` }}
                                                transition={{ duration: 0.4, ease: 'easeOut' }}
                                            />
                                        </div>
                                    </div>
                                </motion.div>
                            ) : (
                                <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-5">
                                    <div className="pb-4 border-b border-gray-100 dark:border-white/5">
                                        <p className="text-xs text-gray-400 mb-1">Query</p>
                                        <p className="text-sm font-medium text-gray-900 dark:text-white leading-snug">&quot;{query}&quot;</p>
                                    </div>
                                    <div>
                                        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Results</p>
                                        <div className="space-y-2">
                                            <div className="flex justify-between text-sm">
                                                <span className="text-gray-500">Total datasets filtered</span>
                                                <span className="font-semibold text-gray-900 dark:text-white">{datasets.length}</span>
                                            </div>
                                            {Object.entries(sourceCounts).map(([src, cnt]) => (
                                                <div key={src} className="flex justify-between text-xs">
                                                    <span className="text-gray-400 capitalize">{src}</span>
                                                    <span className="text-gray-600 dark:text-gray-400">{cnt}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    {/* Agent Intelligence — Reasoning Trace */}
                                    {goalPlan && (
                                        <div className="space-y-3">
                                            <div className="flex items-center gap-2">
                                                <Brain className="w-3.5 h-3.5 text-indigo-500" />
                                                <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Agent Thinking</p>
                                            </div>

                                            {/* Objective */}
                                            {goalPlan.objective && (
                                                <div className="bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-2xl p-3">
                                                    <p className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-1">Objective</p>
                                                    <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{goalPlan.objective}</p>
                                                </div>
                                            )}

                                            {/* Strategy Reasoning */}
                                            {agentPerception?.strategy_reasoning && (
                                                <div className="bg-purple-50 dark:bg-purple-500/10 border border-purple-100 dark:border-purple-500/20 rounded-2xl p-3">
                                                    <p className="text-[10px] font-bold text-purple-500 uppercase tracking-widest mb-1">Strategy</p>
                                                    <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">{agentPerception.strategy_reasoning}</p>
                                                </div>
                                            )}

                                            {/* Tool Pipeline with rationale */}
                                            {goalPlan.search_strategy?.tool_priority && (
                                                <div className="bg-gray-50 dark:bg-white/3 border border-gray-200 dark:border-white/5 rounded-2xl p-3">
                                                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Tool Pipeline</p>
                                                    <div className="flex items-center gap-1 flex-wrap mb-2">
                                                        {goalPlan.search_strategy.tool_priority.map((t, i) => (
                                                            <span key={t} className="flex items-center gap-1">
                                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 font-medium">{t}</span>
                                                                {i < (goalPlan.search_strategy?.tool_priority?.length ?? 0) - 1 && <ChevronRight className="w-2.5 h-2.5 text-gray-300" />}
                                                            </span>
                                                        ))}
                                                    </div>
                                                    {agentPerception?.tool_rationale && (
                                                        <p className="text-[10px] text-gray-500 italic leading-relaxed">{agentPerception.tool_rationale}</p>
                                                    )}
                                                </div>
                                            )}

                                            {/* Modality + Uncertainty badges */}
                                            {agentPerception && (
                                                <div className="flex flex-wrap gap-1.5">
                                                    {agentPerception.modality && agentPerception.modality !== 'unknown' && (
                                                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-blue-600 dark:text-blue-400 font-medium">
                                                            {agentPerception.modality}
                                                        </span>
                                                    )}
                                                    {agentPerception.domain && (
                                                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-medium">
                                                            {agentPerception.domain}
                                                        </span>
                                                    )}
                                                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${agentPerception.uncertainty_level === 'low'
                                                        ? 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-600 dark:text-green-400'
                                                        : agentPerception.uncertainty_level === 'high'
                                                            ? 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400'
                                                            : 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-600 dark:text-amber-400'
                                                        }`}>
                                                        {agentPerception.uncertainty_level} uncertainty
                                                    </span>
                                                </div>
                                            )}

                                            {/* Constraints */}
                                            {agentPerception?.constraints && (
                                                <div className="space-y-1.5">
                                                    {agentPerception.constraints.required_annotations && agentPerception.constraints.required_annotations.length > 0 && (
                                                        <div>
                                                            <p className="text-[10px] text-gray-400 mb-1">Required annotations</p>
                                                            <div className="flex flex-wrap gap-1">
                                                                {agentPerception.constraints.required_annotations.map((a, i) => (
                                                                    <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-amber-600 dark:text-amber-400">{a}</span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                    {agentPerception.constraints.preferred_format && agentPerception.constraints.preferred_format !== 'any' && (
                                                        <p className="text-[10px] text-gray-500">Format: {agentPerception.constraints.preferred_format}</p>
                                                    )}
                                                </div>
                                            )}

                                            {/* Task pills — primary + secondary */}
                                            {agentPerception?.primary_tasks && agentPerception.primary_tasks.length > 0 && (
                                                <div>
                                                    <p className="text-[10px] text-gray-400 mb-1.5">Tasks</p>
                                                    <div className="flex flex-wrap gap-1">
                                                        {agentPerception.primary_tasks.map((t, i) => (
                                                            <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 text-purple-600 dark:text-purple-400 font-medium">{t}</span>
                                                        ))}
                                                        {agentPerception.secondary_tasks?.map((t, i) => (
                                                            <span key={`s${i}`} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-500">{t}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Search Variants */}
                                            {goalPlan.search_strategy?.keyword_variants && goalPlan.search_strategy.keyword_variants.length > 0 && (
                                                <div className="bg-gray-50 dark:bg-white/3 border border-gray-200 dark:border-white/5 rounded-2xl p-3">
                                                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Search Variants</p>
                                                    <div className="flex flex-wrap gap-1">
                                                        {goalPlan.search_strategy.keyword_variants.map((v, i) => (
                                                            <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400">{v}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Risk Notes */}
                                            {agentPerception?.risk_notes && agentPerception.risk_notes.length > 0 && (
                                                <div className="space-y-1">
                                                    {agentPerception.risk_notes.map((note, i) => (
                                                        <div key={i} className="flex items-start gap-1.5">
                                                            <AlertTriangle className="w-3 h-3 text-amber-500 mt-0.5 shrink-0" />
                                                            <p className="text-[10px] text-gray-500 dark:text-gray-500 leading-relaxed">{note}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Self-Adjustment Messages */}
                                    {agentReport?.evaluation?.self_adjustment && agentReport.evaluation.self_adjustment.length > 0 && (
                                        <div className="space-y-2">
                                            <div className="flex items-center gap-2">
                                                <Zap className="w-3.5 h-3.5 text-amber-500" />
                                                <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Agent Adjustments</p>
                                            </div>
                                            {agentReport.evaluation.self_adjustment.map((msg, i) => (
                                                <div key={i} className="bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/15 rounded-2xl p-3">
                                                    <p className="text-[10px] text-amber-700 dark:text-amber-400 leading-relaxed">{msg}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {/* Uncertainty Report */}
                                    {agentReport?.uncertainty && (
                                        <div className="space-y-2">
                                            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Confidence</p>
                                            <div className={`rounded-2xl p-3 text-xs leading-relaxed border ${agentReport.uncertainty.quality_label === 'strong'
                                                ? 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400'
                                                : agentReport.uncertainty.quality_label === 'adequate'
                                                    ? 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-400'
                                                    : 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400'
                                                }`}>
                                                {agentReport.uncertainty.overall}
                                            </div>
                                            {agentReport.uncertainty.known_gaps && agentReport.uncertainty.known_gaps.length > 0 && (
                                                <div className="space-y-1">
                                                    {agentReport.uncertainty.known_gaps.map((gap, i) => (
                                                        <p key={i} className="text-[10px] text-gray-500 dark:text-gray-500 leading-relaxed"> {gap}</p>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {apiError && (
                                        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-2xl p-3">
                                            <p className="text-xs text-red-600 dark:text-red-400 font-medium">Backend Error</p>
                                            <p className="text-xs text-red-500 mt-1">{apiError}</p>
                                        </div>
                                    )}
                                    {status && !apiError && (
                                        <div className="bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-2xl p-3">
                                            <p className="text-xs text-green-600 dark:text-green-400">{status}</p>
                                        </div>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* RIGHT CONTENT */}
                    <div className="flex-1 flex flex-col overflow-hidden">
                        {/* Top bar with filter */}
                        <div className="sticky top-0 z-10 bg-white/80 dark:bg-[#0c0c0e]/80 backdrop-blur-md border-b border-gray-100 dark:border-white/5 px-4 md:px-8 py-3 flex flex-wrap md:flex-nowrap items-center gap-3 shrink-0">
                            <div className="flex items-center gap-2 md:gap-3 h-10 flex-1 w-full max-w-xl bg-gray-50 dark:bg-[#111113] border border-gray-200 dark:border-white/5 rounded-2xl px-4 shadow-sm">
                                <Search className="w-4 h-4 text-gray-400 shrink-0" />
                                <input
                                    type="text"
                                    value={filterText}
                                    onChange={(e) => { setFilterText(e.target.value); setSelectedDataset(null); }}
                                    placeholder="Filter by platform (e.g. kaggle, huggingface)..."
                                    className="flex-1 bg-transparent border-none text-sm text-gray-600 dark:text-gray-300 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none"
                                />
                                {filterText && (
                                    <button onClick={() => setFilterText('')} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                )}
                            </div>
                            {/* Source filter pills */}
                            {!isLoading && availableSources.length > 0 && (
                                <div className="hidden lg:flex items-center gap-1.5">
                                    <button
                                        onClick={() => { setFilterText(''); setSelectedDataset(null); }}
                                        className={`px-3 py-1.5 text-[11px] font-medium rounded-xl border transition-colors ${!filterText
                                            ? 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400'
                                            : 'bg-gray-50 dark:bg-white/5 border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10'}`}
                                    >
                                        All
                                    </button>
                                    {availableSources.map(src => (
                                        <button
                                            key={src}
                                            onClick={() => { setFilterText(filterText === src ? '' : src); setSelectedDataset(null); }}
                                            className={`px-3 py-1.5 text-[11px] font-medium rounded-xl border transition-colors capitalize ${filterText === src
                                                ? 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400'
                                                : 'bg-gray-50 dark:bg-white/5 border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10'}`}
                                        >
                                            {src}
                                        </button>
                                    ))}
                                </div>
                            )}
                            {!isLoading && (
                                <span className="text-xs text-gray-400 shrink-0">{filteredDatasets.length} result{filteredDatasets.length !== 1 ? 's' : ''}</span>
                            )}
                        </div>

                        {/* Main content area */}
                        <div className="flex-1 overflow-y-auto">
                            <AnimatePresence mode="wait">
                                {selectedDataset ? (
                                    /* Inline detail panel — Mac editor style */
                                    <DatasetDetailPanel
                                        key={`detail-${selectedDataset.id}`}
                                        ds={selectedDataset}
                                        onBack={() => setSelectedDataset(null)}
                                    />
                                ) : (
                                    /* Results grid */
                                    <motion.div
                                        key="results-grid"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        className="p-4 md:p-8"
                                    >
                                        {isLoading ? (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                                {[1, 2, 3, 4, 5, 6].map(i => (
                                                    <div key={i} className="h-44 bg-white dark:bg-[#111113] border border-gray-200 dark:border-white/5 rounded-3xl p-5 flex flex-col justify-between relative overflow-hidden">
                                                        <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.8s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/50 dark:via-white/5 to-transparent"></div>
                                                        <div className="flex gap-3">
                                                            <div className="w-10 h-10 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 shrink-0"></div>
                                                            <div className="space-y-2 flex-1">
                                                                <div className="h-4 w-3/4 bg-gray-200 dark:bg-white/5 rounded-xl animate-pulse"></div>
                                                                <div className="h-3 w-full bg-gray-100 dark:bg-white/5 rounded-xl animate-pulse"></div>
                                                                <div className="h-3 w-4/5 bg-gray-100 dark:bg-white/5 rounded-xl animate-pulse"></div>
                                                            </div>
                                                        </div>
                                                        <div className="flex justify-between items-center pt-3 border-t border-gray-100 dark:border-white/5">
                                                            <div className="h-2 w-24 bg-gray-200 dark:bg-white/5 rounded-xl animate-pulse"></div>
                                                            <div className="px-3 py-1 rounded-full bg-indigo-50 dark:bg-white/5 border border-indigo-100 dark:border-white/10 text-[10px] text-indigo-600 dark:text-indigo-400 font-semibold">Auto-Prep</div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : apiError && datasets.length === 0 ? (
                                            <div className="flex flex-col items-center justify-center h-80 gap-4">
                                                <div className="w-16 h-16 rounded-3xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center">
                                                    <X className="w-8 h-8 text-red-500" />
                                                </div>
                                                <h3 className="text-base font-semibold text-gray-900 dark:text-white">Unable to reach backend</h3>
                                                <p className="text-sm text-gray-400 text-center max-w-sm">{apiError}</p>
                                                <Link href="/search" className="text-sm text-indigo-500 hover:underline">← Try a different query</Link>
                                            </div>
                                        ) : filteredDatasets.length === 0 ? (
                                            <div className="flex flex-col items-center justify-center h-80 gap-4">
                                                <Database className="w-10 h-10 text-gray-300" />
                                                <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                                                    {filterText ? 'No matching datasets' : 'No datasets found'}
                                                </h3>
                                                <p className="text-sm text-gray-400">
                                                    {filterText ? `No datasets from "${filterText}". Try a different filter.` : 'Try rephrasing your query.'}
                                                </p>
                                                {filterText ? (
                                                    <button onClick={() => setFilterText('')} className="text-sm text-indigo-500 hover:underline">Clear filter</button>
                                                ) : (
                                                    <Link href="/search" className="text-sm text-indigo-500 hover:underline">← New search</Link>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                                {filteredDatasets.map((ds) => (
                                                    <DatasetCard key={ds.id} ds={ds} onClick={() => setSelectedDataset(ds)} />
                                                ))}
                                            </div>
                                        )}
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function SearchResultsPage() {
    return (
        <Suspense fallback={
            <div className="h-screen w-screen bg-black flex items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            </div>
        }>
            <SearchResultsContent />
        </Suspense>
    );
}
