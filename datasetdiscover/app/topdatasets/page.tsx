'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
    Hexagon, ArrowLeft, ExternalLink, Download, Heart,
    Calendar, Search, Trophy, TrendingUp, AlertCircle,
    ChevronUp, ChevronDown, Tag, Database
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
const PAGE_SIZE = 20;

interface Dataset {
    id: string;
    source: string;
    description: string;
    downloads: number;
    likes: number;
    url: string;
    license: string;
    last_modified: string;
    tags: string[];
    similarity_score: number;
    rank: number;
}

type SortKey = 'rank' | 'downloads' | 'likes' | 'last_modified' | 'score';
type SortDir = 'asc' | 'desc';

function formatNumber(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
}

function LicenseBadge({ license }: { license: string }) {
    const l = license.toLowerCase();
    let cls = 'bg-gray-100 dark:bg-white/5 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-white/10';
    if (['mit', 'apache-2.0', 'cc0-1.0', 'cc-by-4.0', 'openrail'].some(x => l.includes(x)))
        cls = 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20';
    else if (l === 'unknown')
        cls = 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20';
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border truncate max-w-[110px] ${cls}`}>
            {license}
        </span>
    );
}

function RankBadge({ rank }: { rank: number }) {
    if (rank === 1) return <span className="text-base font-black text-amber-400 drop-shadow-sm">#1</span>;
    if (rank === 2) return <span className="text-base font-black text-slate-400">#2</span>;
    if (rank === 3) return <span className="text-sm font-black text-orange-500">#3</span>;
    if (rank <= 10) return <span className="text-sm font-bold text-indigo-400">#{rank}</span>;
    return <span className="text-sm font-semibold text-gray-400 dark:text-gray-600">#{rank}</span>;
}

function SortButton({ label, sortKey, current, dir, onClick }: {
    label: string; sortKey: SortKey; current: SortKey; dir: SortDir; onClick: (k: SortKey) => void;
}) {
    const active = current === sortKey;
    return (
        <button
            onClick={() => onClick(sortKey)}
            className={`flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider transition-colors select-none whitespace-nowrap ${active ? 'text-indigo-500' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'}`}
        >
            {label}
            <span className="flex flex-col leading-none">
                <ChevronUp className={`w-2.5 h-2.5 ${active && dir === 'asc' ? 'text-indigo-500' : 'text-gray-300 dark:text-gray-700'}`} />
                <ChevronDown className={`w-2.5 h-2.5 ${active && dir === 'desc' ? 'text-indigo-500' : 'text-gray-300 dark:text-gray-700'}`} />
            </span>
        </button>
    );
}

function SkeletonRow({ index }: { index: number }) {
    return (
        <div
            className="grid items-center gap-3 px-4 py-3 rounded-2xl border border-transparent"
            style={{ gridTemplateColumns: '52px 1fr 110px 90px 90px 90px 90px 40px', animationDelay: `${index * 60}ms` }}
        >
            <div className="flex justify-center">
                <div className="w-7 h-4 rounded-full bg-gray-200 dark:bg-white/5 animate-pulse" />
            </div>
            <div className="space-y-2">
                <div className="h-3.5 w-2/5 rounded-full bg-gray-200 dark:bg-white/8 animate-pulse" />
                <div className="h-2.5 w-4/5 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
                <div className="flex gap-1 mt-1">
                    <div className="h-4 w-14 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
                    <div className="h-4 w-10 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
                    <div className="h-4 w-16 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
                </div>
            </div>
            <div className="h-4 w-16 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
            <div className="h-4 w-10 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
            <div className="h-4 w-14 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
            <div className="h-4 w-10 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
            <div className="h-4 w-16 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
            <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-white/5 animate-pulse" />
        </div>
    );
}

export default function TopDatasetsPage() {
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState('');
    const [sortKey, setSortKey] = useState<SortKey>('rank');
    const [sortDir, setSortDir] = useState<SortDir>('asc');
    const [tagFilter, setTagFilter] = useState<string>('');
    const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
    const sentinelRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        async function fetchDatasets() {
            try {
                const res = await fetch(`${API_BASE}/api/projects/top100`);
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                const data = await res.json();
                setDatasets(
                    (data.datasets || []).map((d: Omit<Dataset, 'rank'>, i: number) => ({ ...d, rank: i + 1 }))
                );
            } catch (e: unknown) {
                setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }
        fetchDatasets();
    }, []);

    useEffect(() => { setVisibleCount(PAGE_SIZE); }, [filter, tagFilter, sortKey, sortDir]);

    const handleIntersect = useCallback((entries: IntersectionObserverEntry[]) => {
        if (entries[0].isIntersecting) setVisibleCount(prev => prev + PAGE_SIZE);
    }, []);

    useEffect(() => {
        const el = sentinelRef.current;
        if (!el) return;
        const observer = new IntersectionObserver(handleIntersect, { threshold: 0.1 });
        observer.observe(el);
        return () => observer.disconnect();
    }, [handleIntersect, loading]);

    const allTags = useMemo(() => {
        const count = new Map<string, number>();
        datasets.forEach(d => d.tags.forEach(t => count.set(t, (count.get(t) ?? 0) + 1)));
        return Array.from(count.entries()).sort((a, b) => b[1] - a[1]).slice(0, 16).map(([tag]) => tag);
    }, [datasets]);

    const handleSort = (key: SortKey) => {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('desc'); }
    };

    const filtered = useMemo(() => {
        let list = [...datasets];
        if (filter.trim()) {
            const q = filter.toLowerCase();
            list = list.filter(d =>
                d.id.toLowerCase().includes(q) ||
                d.description.toLowerCase().includes(q) ||
                d.tags.some(t => t.toLowerCase().includes(q))
            );
        }
        if (tagFilter) list = list.filter(d => d.tags.includes(tagFilter));
        list = [...list].sort((a, b) => {
            let av: number, bv: number;
            if (sortKey === 'downloads') { av = a.downloads; bv = b.downloads; }
            else if (sortKey === 'likes') { av = a.likes; bv = b.likes; }
            else if (sortKey === 'score') { av = a.similarity_score; bv = b.similarity_score; }
            else if (sortKey === 'last_modified') {
                av = new Date(a.last_modified || 0).getTime();
                bv = new Date(b.last_modified || 0).getTime();
            } else { av = a.rank; bv = b.rank; }
            return sortDir === 'desc' ? bv - av : av - bv;
        });
        return list;
    }, [datasets, filter, tagFilter, sortKey, sortDir]);

    const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);
    const hasMore = visibleCount < filtered.length;
    const totalDownloads = useMemo(() => datasets.reduce((s, d) => s + d.downloads, 0), [datasets]);
    const totalLikes = useMemo(() => datasets.reduce((s, d) => s + d.likes, 0), [datasets]);

    const COL = '52px 1fr 110px 90px 90px 90px 90px 40px';

    return (
        <div className="h-screen w-screen bg-black p-2 md:p-3 overflow-hidden flex flex-col">
            <div className="flex-1 bg-[#FAFAFA] dark:bg-[#0c0c0e] rounded-2xl md:rounded-3xl border border-gray-200 dark:border-white/10 flex flex-col overflow-hidden shadow-2xl">

                {/* Header */}
                <div className="relative flex h-16 border-b border-gray-100 dark:border-white/5 bg-white dark:bg-[#111113] items-center px-4 md:px-6 justify-between shrink-0">
                    <div className="flex items-center gap-2 md:gap-4">
                        <div className="hidden sm:flex flex-row gap-2 items-center mr-1">
                            <div className="w-3.5 h-3.5 rounded-full bg-[#FF5F56] border border-[#E0443E]" />
                            <div className="w-3.5 h-3.5 rounded-full bg-[#FFBD2E] border border-[#DEA123]" />
                            <div className="w-3.5 h-3.5 rounded-full bg-[#27C93F] border border-[#1AAB29]" />
                        </div>
                        <Link href="/search" className="flex items-center gap-2 px-3 py-1.5 md:px-4 md:py-2 rounded-full bg-gray-50 dark:bg-white/5 hover:bg-gray-100 dark:hover:bg-white/10 text-gray-700 dark:text-gray-300 transition-colors text-xs md:text-sm font-semibold">
                            <ArrowLeft className="w-4 h-4" />
                            <span className="hidden sm:inline">Back to Search</span>
                        </Link>
                    </div>
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="hidden md:flex h-9 px-5 items-center justify-center rounded-full bg-gray-50 dark:bg-black border border-gray-200 dark:border-white/10 text-xs font-mono text-gray-500 shadow-inner whitespace-nowrap">
                            ranqora / top datasets
                        </div>
                    </div>
                    <div className="hidden sm:flex items-center gap-2 opacity-70">
                        <Hexagon className="w-4 h-4 text-indigo-500" />
                        <span className="text-xs font-bold text-gray-900 dark:text-white tracking-wider uppercase">Ranqora</span>
                    </div>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto">

                    {/* Hero */}
                    <div className="relative px-8 pt-10 pb-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50/60 dark:from-indigo-950/30 dark:via-[#0c0c0e] dark:to-purple-950/20 border-b border-gray-100 dark:border-white/5 overflow-hidden">
                        <div className="absolute inset-0 opacity-[0.04] dark:opacity-[0.07]"
                            style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, #6366f1 1px, transparent 0)', backgroundSize: '28px 28px' }} />
                        <div className="relative max-w-3xl mx-auto text-center">
                            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-xs font-bold uppercase tracking-widest mb-5">
                                <Trophy className="w-3.5 h-3.5" />
                                Platform Leaderboard
                            </div>
                            <h1 className="text-3xl md:text-4xl font-black text-gray-900 dark:text-white tracking-tight mb-2">
                                Top Datasets
                            </h1>
                            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-lg mx-auto mb-7">
                                The most downloaded and highest-rated open datasets ranked by community adoption.
                            </p>
                            {!loading && !error && (
                                <div className="flex items-center justify-center gap-8 flex-wrap">
                                    {[
                                        { icon: Database, label: 'Datasets', value: datasets.length.toString() },
                                        { icon: Download, label: 'Total Downloads', value: formatNumber(totalDownloads) },
                                        { icon: Heart, label: 'Total Likes', value: formatNumber(totalLikes) },
                                        { icon: TrendingUp, label: 'Source', value: 'HuggingFace/Kaggle' },
                                    ].map(({ icon: Icon, label, value }) => (
                                        <div key={label} className="flex flex-col items-center gap-1 min-w-[80px]">
                                            <div className="flex items-center gap-1.5 text-[10px] text-gray-400 uppercase tracking-widest">
                                                <Icon className="w-3 h-3" />{label}
                                            </div>
                                            <span className="text-xl font-black text-gray-900 dark:text-white tabular-nums">{value}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Controls */}
                    <div className="sticky top-0 z-20 bg-white/95 dark:bg-[#111113]/95 backdrop-blur-md border-b border-gray-100 dark:border-white/5">
                        <div className="px-6 pt-3 pb-2 flex items-center gap-4">
                            <div className="flex items-center gap-2 flex-1 max-w-xs h-9 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-full px-4 shadow-sm">
                                <Search className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                                <input
                                    type="text"
                                    value={filter}
                                    onChange={e => setFilter(e.target.value)}
                                    placeholder="Filter datasets…"
                                    className="bg-transparent text-sm text-gray-700 dark:text-gray-300 placeholder-gray-400 outline-none flex-1 min-w-0"
                                />
                            </div>
                            <span className="ml-auto text-xs text-gray-400 shrink-0 tabular-nums">
                                {loading ? '—' : `${visible.length} / ${filtered.length}`}
                            </span>
                        </div>
                        <div className="px-6 pb-3 flex items-center gap-2 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
                            <span className="text-[10px] text-gray-400 shrink-0 flex items-center gap-1 uppercase tracking-wider">
                                <Tag className="w-3 h-3" /> Filter:
                            </span>
                            <button
                                onClick={() => setTagFilter('')}
                                className={`text-[10px] px-3 py-1 rounded-full border shrink-0 transition-colors font-semibold ${!tagFilter ? 'bg-indigo-500 border-indigo-500 text-white shadow-sm' : 'bg-gray-50 dark:bg-white/5 border-gray-200 dark:border-white/10 text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10'}`}
                            >All</button>
                            {allTags.map((tag, ti) => (
                                <button
                                    key={`tag-pill-${ti}-${tag}`}
                                    onClick={() => setTagFilter(tag === tagFilter ? '' : tag)}
                                    className={`text-[10px] px-3 py-1 rounded-full border shrink-0 transition-colors font-medium whitespace-nowrap ${tag === tagFilter ? 'bg-indigo-500 border-indigo-500 text-white shadow-sm' : 'bg-gray-50 dark:bg-white/5 border-gray-200 dark:border-white/10 text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10'}`}
                                >
                                    {tag}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Responsive Data Table */}
                    <div className="overflow-x-auto w-full">
                        <div className="min-w-[900px]">
                            {/* Table header */}
                            {!loading && !error && filtered.length > 0 && (
                                <div className="px-4 md:px-6 pt-4 pb-1">
                                    <div className="grid items-center gap-3 pb-2 border-b border-gray-100 dark:border-white/5"
                                        style={{ gridTemplateColumns: COL }}>
                                        <SortButton label="#" sortKey="rank" current={sortKey} dir={sortDir} onClick={handleSort} />
                                        <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">Dataset</span>
                                        <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">License</span>
                                        <SortButton label="Score" sortKey="score" current={sortKey} dir={sortDir} onClick={handleSort} />
                                        <SortButton label="Downloads" sortKey="downloads" current={sortKey} dir={sortDir} onClick={handleSort} />
                                        <SortButton label="Likes" sortKey="likes" current={sortKey} dir={sortDir} onClick={handleSort} />
                                        <SortButton label="Updated" sortKey="last_modified" current={sortKey} dir={sortDir} onClick={handleSort} />
                                        <span />
                                    </div>
                                </div>
                            )}

                            {/* Rows */}
                            <div className="px-4 md:px-6 pb-8 pt-1">
                                {loading ? (
                                    <div className="space-y-0.5 mt-2">
                                        {Array.from({ length: 12 }).map((_, i) => (
                                            <SkeletonRow key={`skeleton-${i}`} index={i} />
                                        ))}
                                    </div>
                                ) : error ? (
                                    <div className="flex flex-col items-center justify-center h-64 gap-4">
                                        <div className="w-16 h-16 rounded-[32px] bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center">
                                            <AlertCircle className="w-8 h-8 text-red-500" />
                                        </div>
                                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Could not load datasets</p>
                                        <p className="text-xs text-gray-400 text-center max-w-xs">{error}</p>
                                        <button onClick={() => window.location.reload()} className="text-xs text-indigo-500 hover:underline">Try again</button>
                                    </div>
                                ) : filtered.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-48 gap-3">
                                        <Search className="w-8 h-8 text-gray-300" />
                                        <p className="text-sm text-gray-500">No datasets match your filter</p>
                                        <button onClick={() => { setFilter(''); setTagFilter(''); }} className="text-xs text-indigo-500 hover:underline">Clear filters</button>
                                    </div>
                                ) : (
                                    <>
                                        <div className="space-y-0.5 mt-1">
                                            <AnimatePresence initial={false}>
                                                {visible.map((ds, visIdx) => (
                                                    <motion.div
                                                        key={`${ds.id}-${ds.rank}`}
                                                        layout
                                                        initial={{ opacity: 0, y: 6 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        exit={{ opacity: 0, scale: 0.98 }}
                                                        transition={{ duration: 0.15, delay: Math.min(visIdx * 0.006, 0.25) }}
                                                        className={`group grid items-center gap-3 px-4 py-3 rounded-2xl border transition-all ${ds.rank === 1
                                                            ? 'border-amber-200 dark:border-amber-500/25 bg-amber-50/60 dark:bg-amber-500/5 hover:bg-amber-100 dark:hover:bg-amber-500/15'
                                                            : ds.rank <= 3
                                                                ? 'border-indigo-200/60 dark:border-indigo-500/15 bg-indigo-50/40 dark:bg-indigo-500/5 hover:bg-indigo-100 dark:hover:bg-indigo-500/15'
                                                                : 'border-transparent hover:border-gray-200/80 dark:hover:border-white/8 hover:bg-white dark:hover:bg-white/[0.05]'
                                                            }`}
                                                        style={{ gridTemplateColumns: COL }}
                                                    >
                                                        <div className="flex items-center justify-center">
                                                            <RankBadge rank={ds.rank} />
                                                        </div>

                                                        <div className="min-w-0">
                                                            <div className="flex items-center gap-2 mb-0.5">
                                                                <p className="text-sm font-bold text-gray-900 dark:text-white truncate leading-tight">{ds.id}</p>
                                                                {ds.rank <= 3 && (
                                                                    <Trophy className={`w-3.5 h-3.5 shrink-0 ${ds.rank === 1 ? 'text-amber-400' : ds.rank === 2 ? 'text-slate-400' : 'text-orange-500'}`} />
                                                                )}
                                                            </div>
                                                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate leading-relaxed">{ds.description}</p>
                                                            {ds.tags.length > 0 && (
                                                                <div className="flex gap-1 mt-1.5 flex-wrap">
                                                                    {ds.tags.slice(0, 3).map((t, ti) => (
                                                                        <span key={`${ds.id}-tag-${ti}-${t}`} className="text-[9px] px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-white/5 text-gray-500 border border-gray-200 dark:border-white/10">
                                                                            {t}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>

                                                        <div className="flex items-center">
                                                            <LicenseBadge license={ds.license} />
                                                        </div>

                                                        <div className="flex items-center gap-1.5">
                                                            <span className={`text-sm font-bold tabular-nums ${ds.similarity_score >= 0.7 ? 'text-green-500' : ds.similarity_score >= 0.4 ? 'text-indigo-500' : 'text-gray-400'}`}>
                                                                {Math.round(ds.similarity_score * 100)}<span className="text-[10px] font-normal ml-0.5 opacity-60">%</span>
                                                            </span>
                                                        </div>

                                                        <div className="flex items-center gap-1.5">
                                                            <Download className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                                                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 tabular-nums">{formatNumber(ds.downloads)}</span>
                                                        </div>

                                                        <div className="flex items-center gap-1.5">
                                                            <Heart className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                                                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 tabular-nums">{formatNumber(ds.likes)}</span>
                                                        </div>

                                                        <div className="flex items-center gap-1.5 text-xs text-gray-400">
                                                            <Calendar className="w-3 h-3 shrink-0" />
                                                            <span className="tabular-nums">
                                                                {ds.last_modified ? new Date(ds.last_modified).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                                                            </span>
                                                        </div>

                                                        <a
                                                            href={ds.url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            onClick={e => e.stopPropagation()}
                                                            className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 dark:bg-white/5 hover:bg-indigo-500 hover:text-white text-gray-400 dark:text-gray-500 transition-all opacity-0 group-hover:opacity-100"
                                                            title={`Open ${ds.id} on HuggingFace`}
                                                        >
                                                            <ExternalLink className="w-3.5 h-3.5" />
                                                        </a>
                                                    </motion.div>
                                                ))}
                                            </AnimatePresence>
                                        </div>

                                        {hasMore && (
                                            <div ref={sentinelRef} className="space-y-0.5 mt-0.5">
                                                {Array.from({ length: Math.min(PAGE_SIZE, filtered.length - visibleCount) }).map((_, i) => (
                                                    <SkeletonRow key={`lazy-skeleton-${visibleCount + i}`} index={i} />
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
