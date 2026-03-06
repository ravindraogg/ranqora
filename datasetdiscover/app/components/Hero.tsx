'use client';

import { motion } from 'framer-motion';
import { ChevronRight, Database, Search } from 'lucide-react';
import Link from 'next/link';
import { cn } from '../lib/utils';

export function Hero() {
    return (
        <div className="relative overflow-hidden bg-white dark:bg-black pt-32 pb-20 lg:pt-48 lg:pb-32">
            {/* Abstract Background - Gradient & Grid inspired by the reference images */}
            <div className="absolute inset-0 z-0">
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]"></div>
                <div className="absolute top-0 right-0 -mr-40 -mt-40 w-96 h-96 bg-indigo-500/30 rounded-full blur-3xl opacity-50 dark:opacity-30"></div>
                <div className="absolute bottom-0 left-0 -ml-40 -mb-40 w-96 h-96 bg-blue-500/30 rounded-full blur-3xl opacity-50 dark:opacity-30"></div>
            </div>

            <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">


                <motion.h1
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="text-7xl sm:text-8xl md:text-[10vw] leading-[0.99] font-black tracking-tighter text-transparent bg-clip-text bg-center bg-cover mb-10 pb-6 lowercase drop-shadow-2xl dark:drop-shadow-none"
                    style={{ backgroundImage: "url('https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=2670&auto=format&fit=crop')" }}
                >
                    dataset<br />intelligence<br />reimagined.
                </motion.h1>

                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="max-w-2xl mx-auto text-lg md:text-xl text-gray-600 dark:text-gray-300 mb-10"
                >
                    Accelerate your AI pipelines. Discover, prepare, and evaluate high-quality datasets through a single enterprise-ready intelligence platform.
                </motion.p>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.3 }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-4"
                >
                    <Link
                        href="/topdatasets"
                        className="w-full sm:w-auto px-8 py-4 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-lg transition-all shadow-lg hover:shadow-indigo-500/25 flex items-center justify-center gap-2"
                    >
                        <Search className="w-5 h-5" />
                        Explore Datasets
                    </Link>
                    <Link
                        href="#demo"
                        className="w-full sm:w-auto px-8 py-4 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-white/10 font-semibold text-lg transition-all flex items-center justify-center gap-2 group"
                    >
                        <Database className="w-5 h-5 text-gray-500" />
                        Connect Data Hub
                        <ChevronRight className="w-5 h-5 text-gray-400 group-hover:translate-x-1 transition-transform" />
                    </Link>
                </motion.div>

                {/* Floating preview element */}
                <motion.div
                    initial={{ opacity: 0, y: 40 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, delay: 0.5 }}
                    className="mt-16 sm:mt-24 lg:mt-32 relative max-w-5xl mx-auto"
                >
                    <div className="absolute -inset-1 rounded-2xl bg-gradient-to-tr from-indigo-500 to-blue-500 blur-xl opacity-20"></div>
                    <div className="relative rounded-2xl bg-white dark:bg-[#09090b] border border-gray-200 dark:border-gray-800 shadow-2xl overflow-hidden aspect-[16/9]">
                        {/* Fake Dashboard UI */}
                        <div className="flex h-12 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-white/5 items-center px-4 gap-2">
                            <div className="flex gap-1.5">
                                <div className="w-3 h-3 rounded-full bg-red-400/80"></div>
                                <div className="w-3 h-3 rounded-full bg-amber-400/80"></div>
                                <div className="w-3 h-3 rounded-full bg-green-400/80"></div>
                            </div>
                            <div className="mx-auto flex h-6 items-center rounded-md bg-white dark:bg-black px-4 md:px-12 lg:px-24 border border-gray-200 dark:border-gray-800 text-[10px] text-gray-400">
                                ranqora / search
                            </div>
                        </div>

                        <div className="p-8 flex h-[calc(100%-3rem)] bg-[#FAFAFA] dark:bg-[#09090b]">
                            <div className="w-1/4 space-y-4 pr-6 border-r border-gray-200 dark:border-gray-800">
                                <div className="h-6 w-1/2 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                                <div className="h-4 w-full bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                                <div className="h-4 w-3/4 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                                <div className="h-4 w-5/6 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                            </div>
                            <div className="flex-1 pl-8 space-y-6">
                                <div className="flex gap-4">
                                    <div className="h-10 flex-1 bg-white dark:bg-black border border-gray-200 dark:border-gray-800 shadow-sm rounded-lg flex items-center px-4">
                                        <Search className="w-4 h-4 text-gray-300 mr-2" />
                                        <div className="h-4 w-32 bg-gray-200 dark:bg-gray-800/50 rounded animate-pulse"></div>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    {[1, 2, 3, 4].map((i) => (
                                        <div key={i} className="h-32 bg-white dark:bg-black border border-gray-200 dark:border-gray-800 rounded-lg p-4 flex flex-col justify-between">
                                            <div className="flex gap-2">
                                                <div className="w-8 h-8 rounded bg-indigo-100 dark:bg-indigo-900/30 shrink-0"></div>
                                                <div className="space-y-2 w-full">
                                                    <div className="h-4 w-1/2 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                                                    <div className="h-3 w-3/4 bg-gray-100 dark:bg-gray-900 rounded animate-pulse"></div>
                                                </div>
                                            </div>
                                            <div className="flex justify-between items-end">
                                                <div className="h-2 w-16 bg-gray-200 dark:bg-gray-800 rounded"></div>
                                                <div className="h-6 w-16 rounded-full bg-indigo-50 dark:bg-white/5 border border-indigo-100 dark:border-white/10 text-[10px] flex items-center justify-center text-indigo-600 dark:text-indigo-400 font-medium">Auto-Prep</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                    </div>
                </motion.div>
            </div>
        </div>
    );
}
