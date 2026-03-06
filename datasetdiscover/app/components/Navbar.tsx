'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Menu, X, Hexagon, Moon, Sun, ChevronDown, Database, Zap, FileText, Brain, Globe, Code, Shield, CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence, useScroll, useSpring } from 'framer-motion';
import { useTheme } from 'next-themes';

const tools = [
    { name: 'Kaggle', icon: Database, color: 'text-blue-500', href: '#tools' },
    { name: 'HuggingFace', icon: Zap, color: 'text-yellow-500', href: '#tools' },
    { name: 'ArXiv', icon: FileText, color: 'text-red-500', href: '#tools' },
    { name: 'IEEE Xplore', icon: Shield, color: 'text-indigo-500', href: '#tools' },
    { name: 'Semantic Scholar', icon: Brain, color: 'text-cyan-500', href: '#tools' },
    { name: 'OpenDataPortal', icon: Globe, color: 'text-emerald-500', href: '#tools' },
    { name: 'GitHub', icon: Code, color: 'text-gray-500', href: '#tools' },
];

export function Navbar() {
    const [isOpen, setIsOpen] = useState(false);
    const [isToolsOpen, setIsToolsOpen] = useState(false);
    const { theme, setTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    // Track scroll for the glowing border
    const { scrollYProgress } = useScroll();
    const pathLength = useSpring(scrollYProgress, {
        stiffness: 100,
        damping: 30,
        restDelta: 0.001
    });

    useEffect(() => {
        setMounted(true);
    }, []);

    return (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 w-full max-w-5xl px-4 z-50">
            <div className="relative flex items-center justify-between gap-2 md:gap-4 p-1">


                {/* Card 1: Logo */}
                <div className="h-14 px-6 flex items-center justify-center rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg shrink-0">
                    <Link href="/" className="flex items-center gap-2">
                        <Hexagon className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                        <span className="font-bold text-lg tracking-tight text-gray-900 dark:text-white flex items-baseline gap-1.5">
                            Ranqora
                        </span>
                    </Link>
                </div>

                {/* Card 2: Nav Links */}
                <div className="relative hidden md:flex flex-1 h-14 px-8 items-center justify-center space-x-8 rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg">
                    {/* Animated Glowing Perimeter Border for Card 2 */}
                    <div className="absolute inset-0 pointer-events-none rounded-full overflow-hidden z-[-1]">
                        <svg className="w-full h-full" width="100%" height="100%">
                            <motion.rect
                                x="1" y="1" width="calc(100% - 2px)" height="calc(100% - 2px)"
                                rx="28" ry="28"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                className="text-indigo-500/30"
                                style={{
                                    pathLength,
                                    filter: 'drop-shadow(0 0 8px rgba(99,102,241,0.5))'
                                }}
                            />
                        </svg>
                    </div>

                    <Link href="#features" className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors">
                        Features
                    </Link>

                    {/* Tools Dropdown */}
                    <div
                        className="relative"
                        onMouseEnter={() => setIsToolsOpen(true)}
                        onMouseLeave={() => setIsToolsOpen(false)}
                    >
                        <button className="flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors py-4">
                            Tools
                            <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isToolsOpen ? 'rotate-180' : ''}`} />
                        </button>

                        <AnimatePresence>
                            {isToolsOpen && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                    exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                    className="absolute top-full left-1/2 -translate-x-1/2 w-64 mt-1 p-2 rounded-3xl bg-white/95 dark:bg-black/95 backdrop-blur-xl border border-gray-200/40 dark:border-white/10 shadow-2xl overflow-hidden"
                                >
                                    <div className="grid grid-cols-1 gap-1">
                                        {tools.map((tool) => (
                                            <Link
                                                key={tool.name}
                                                href={tool.href}
                                                className="flex items-center gap-3 p-3 rounded-2xl hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
                                            >
                                                <div className={`w-8 h-8 rounded-xl bg-gray-100 dark:bg-white/5 flex items-center justify-center ${tool.color} group-hover:scale-110 transition-transform`}>
                                                    <tool.icon className="w-4 h-4" />
                                                </div>
                                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                                                    {tool.name}
                                                </span>
                                            </Link>
                                        ))}
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>

                    <Link href="#steps" className="flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors">
                        <CheckCircle2 className="w-3.5 h-3.5 text-indigo-500" />
                        Steps
                    </Link>
                </div>

                {/* Card 3: Theme Toggle & Get Started */}
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        className="h-14 w-14 flex items-center justify-center rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
                    >
                        {mounted ? (
                            theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />
                        ) : (
                            <div className="h-5 w-5" />
                        )}
                        <span className="sr-only">Toggle theme</span>
                    </button>

                    <Link
                        href="/search"
                        className="hidden sm:flex h-14 px-8 items-center justify-center rounded-full bg-gray-900 text-white dark:bg-white dark:text-black text-sm font-bold hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors shadow-lg shadow-gray-900/20 dark:shadow-white/20"
                    >
                        Get Started
                    </Link>

                    <button
                        onClick={() => setIsOpen(!isOpen)}
                        className="md:hidden h-14 w-14 flex items-center justify-center rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
                    >
                        <span className="sr-only">Open main menu</span>
                        {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                    </button>
                </div>
            </div>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="md:hidden mt-4 rounded-[2.5rem] bg-white/95 dark:bg-black/95 backdrop-blur-xl border border-gray-200/40 dark:border-white/10 shadow-xl overflow-hidden"
                    >
                        <div className="px-4 py-6 space-y-2">
                            <Link href="#features" onClick={() => setIsOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-2xl text-base font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
                                <Hexagon className="w-5 h-5 text-indigo-500" />
                                Features
                            </Link>

                            <div className="px-4 py-2">
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 ml-1">Tools</p>
                                <div className="grid grid-cols-2 gap-2">
                                    {tools.map((tool) => (
                                        <Link
                                            key={tool.name}
                                            href={tool.href}
                                            onClick={() => setIsOpen(false)}
                                            className="flex items-center gap-2 p-2 rounded-xl bg-gray-50 dark:bg-white/5 text-sm text-gray-600 dark:text-gray-400"
                                        >
                                            <tool.icon className={`w-3.5 h-3.5 ${tool.color}`} />
                                            {tool.name}
                                        </Link>
                                    ))}
                                </div>
                            </div>

                            <Link href="#steps" onClick={() => setIsOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-2xl text-base font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
                                <CheckCircle2 className="w-5 h-5 text-indigo-500" />
                                Steps
                            </Link>

                            <div className="pt-4 px-4">
                                <Link href="/search" onClick={() => setIsOpen(false)} className="flex items-center justify-center px-4 py-4 w-full bg-gray-900 dark:bg-white text-white dark:text-black rounded-2xl text-base font-bold shadow-lg shadow-indigo-500/10">
                                    Get Started
                                </Link>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
