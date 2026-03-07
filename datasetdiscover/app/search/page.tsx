'use client';

import { useState, useEffect, useRef } from 'react';
import { BrainCircuit, Hexagon, ArrowLeft, Loader2, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

const examplePrompts = [
    "Sentiment analysis for social media text",
    "Time series for energy forecasting",
    "Medical imaging X-ray with bounding boxes",
];

export default function SearchDashboard() {
    const [query, setQuery] = useState('');
    const [clientId, setClientId] = useState<string | null>(null);
    const [authError, setAuthError] = useState<string | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [isLoadingAuth, setIsLoadingAuth] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [shake, setShake] = useState(false);
    const router = useRouter();

    // Step 1: On mount, fetch client_id from backend. 
    // Optimization: Check for existing session first to avoid jitter on fast inputs
    useEffect(() => {
        const stored = sessionStorage.getItem('ranqora_client_id');
        if (stored) {
            setClientId(stored);
            setIsLoadingAuth(false);
        }

        async function fetchClientId() {
            try {
                const res = await fetch(`${API_BASE}/api/auth/client_id`);
                if (!res.ok) throw new Error(`Server responded ${res.status}`);
                const data = await res.json();
                setClientId(data.client_id);
                sessionStorage.setItem('ranqora_client_id', data.client_id);
                setAuthError(null);
            } catch (e: unknown) {
                // Only show error if we don't even have a stored ID
                if (!stored) {
                    setAuthError(`Could not reach backend: ${(e as Error).message}`);
                }
            } finally {
                setIsLoadingAuth(false);
            }
        }
        fetchClientId();
    }, []);

    // Auto-resize textarea up to 5 lines
    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = 'auto';
        const lineHeight = 28;
        const maxHeight = lineHeight * 5;
        el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px';
        el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }, [query]);

    const handleParseQuery = () => {
        if (!query.trim()) {
            setShake(true);
            setTimeout(() => setShake(false), 500);
            return;
        }
        if (!clientId) {
            setAuthError('No client session. Please refresh the page.');
            return;
        }
        setIsSubmitting(true);
        router.push(`/search/results?q=${encodeURIComponent(query.trim())}&cid=${encodeURIComponent(clientId)}`);
    };

    return (
        <div className="min-h-screen bg-white dark:bg-[#09090b] flex flex-col">
            {/* Minimal Navbar */}
            <div className="fixed top-4 md:top-6 left-1/2 -translate-x-1/2 w-full max-w-7xl px-4 md:px-8 z-50 flex justify-between items-center gap-2">
                <div className="h-12 md:h-14 px-4 md:px-6 flex items-center justify-center rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg shrink-0">
                    <Link href="/" className="flex items-center gap-2">
                        <Hexagon className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                        <span className="font-bold text-lg tracking-tight text-gray-900 dark:text-white">Ranqora</span>
                    </Link>
                </div>
                <Link
                    href="/"
                    className="h-12 md:h-14 px-4 md:px-6 flex items-center justify-center gap-2 rounded-full border border-gray-200/40 bg-white dark:bg-white dark:border-white/10 shadow-lg text-gray-900 dark:text-black hover:bg-gray-50 dark:hover:bg-gray-200 transition-colors shrink-0 font-bold text-xs md:text-sm"
                >
                    <ArrowLeft className="w-4 h-4" />
                    <span>Go Back</span>
                </Link>
            </div>

            {/* Main Layout: Now using flex-row for side-by-side positioning */}
            <div className="flex-1 flex flex-col lg:flex-row items-center justify-between px-6 md:px-12 lg:px-20 pt-28 md:pt-32 pb-12 gap-8 md:gap-12 max-w-[1600px] mx-auto w-full">

                {/* LEFT: Hero text section */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5 }}
                    className="w-full lg:w-1/2 flex flex-col items-start"
                >
                    <h2
                        className="font-black tracking-tighter text-transparent bg-clip-text bg-center bg-cover lowercase leading-[0.90] drop-shadow-2xl dark:drop-shadow-none pb-4 mb-[5px] pr-4"
                        style={{
                            backgroundImage: "url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop')",
                            fontSize: 'clamp(3.5rem, 11vw, 10rem)'
                        }}
                    >
                        search.<br />discover.
                    </h2>
                    <p className="mt-5 text-base md:text-lg text-gray-500 dark:text-gray-400 max-w-md">
                        Describe your project. Ranqora analyzes context and ranks the most relevant datasets using semantic and graph intelligence.
                    </p>
                </motion.div>

                {/* RIGHT: Prompts + Input */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, delay: 0.15 }}
                    className="w-full lg:w-1/2 flex flex-col gap-4"
                >
                    {/* Auth status indicator */}
                    <div className="flex items-center gap-2 h-5">
                        {isLoadingAuth && (
                            <span className="flex items-center gap-1.5 text-xs text-gray-400">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Connecting to Ranqora network...
                            </span>
                        )}
                        {authError && (
                            <span className="flex items-center gap-1.5 text-xs text-red-500">
                                <AlertCircle className="h-3 w-3" />
                                {authError}
                            </span>
                        )}
                        {!isLoadingAuth && clientId && !authError && (
                            <span className="flex items-center gap-1.5 text-xs text-emerald-500">
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                System Ready
                            </span>

                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1.5 text-xs text-gray-400">

                            Try Examples
                        </span>
                    </div>
                    {/* Example Prompts */}
                    <div className="flex flex-wrap gap-2 mb-2">
                        {examplePrompts.map((p) => (
                            <button
                                key={p}
                                onClick={() => setQuery(p)}
                                className="px-3 py-1.5 text-xs rounded-full border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
                            >
                                {p}
                            </button>
                        ))}
                    </div>

                    {/* Main Input Box */}
                    <motion.div
                        animate={shake ? { x: [-10, 10, -10, 10, 0] } : {}}
                        transition={{ duration: 0.4 }}
                        className="relative group bg-white dark:bg-[#0A0A0A] border border-gray-200 dark:border-white/10 rounded-3xl p-3 shadow-2xl focus-within:border-indigo-500/50 transition-all"
                    >
                        <textarea
                            ref={textareaRef}
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    handleParseQuery();
                                }
                            }}
                            placeholder="Describe your dataset needs..."
                            className="w-full bg-transparent border-none focus:ring-0 text-lg md:text-xl text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 resize-none min-h-[120px] max-h-[300px] p-4"
                        />
                        <div className="flex justify-end pt-2 pr-2 pb-1">
                            <button
                                onClick={handleParseQuery}
                                disabled={isLoadingAuth || isSubmitting || !!authError}
                                className={`flex-none flex items-center justify-center gap-2 rounded-xl h-10 px-6 font-medium transition-colors shadow-sm mb-1 shrink-0 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-[#0A0A0A] ${isLoadingAuth || isSubmitting || authError
                                    ? 'bg-gray-300 dark:bg-white/10 cursor-not-allowed text-gray-500 dark:text-gray-600'
                                    : 'bg-gray-900 dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-200'
                                    }`}
                            >
                                {isLoadingAuth ? (
                                    <Loader2 className="h-5 w-5 animate-spin" />
                                ) : isSubmitting ? (
                                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                ) : (
                                    <BrainCircuit className="h-5 w-5" />
                                )}
                                {isLoadingAuth ? 'Connecting...' : isSubmitting ? 'Redirecting...' : 'Parse query'}
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            </div>
        </div>
    );
}