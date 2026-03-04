'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Menu, X, Hexagon, Moon, Sun } from 'lucide-react';
import { motion, AnimatePresence, useScroll, useSpring } from 'framer-motion';
import { useTheme } from 'next-themes';

export function Navbar() {
    const [isOpen, setIsOpen] = useState(false);
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
                        <span className="font-bold text-lg tracking-tight text-gray-900 dark:text-white">
                            Ranqora
                        </span>
                    </Link>
                </div>

                {/* Card 2: Nav Links */}
                <div className="relative hidden md:flex flex-1 h-14 px-8 items-center justify-center space-x-8 rounded-full border border-gray-200/40 bg-white/70 dark:bg-black/70 dark:border-white/10 backdrop-blur-md shadow-lg">
                    {/* Animated Glowing Perimeter Border for Card 2 */}
                    <div className="absolute inset-0 pointer-events-none rounded-full overflow-visible z-[-1]">
                        <svg className="w-full h-full overflow-visible" width="100%" height="100%">
                            <motion.rect
                                x="0"
                                y="0"
                                width="100%"
                                height="100%"
                                rx="27"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                className="text-indigo-500"
                                style={{
                                    pathLength,
                                    filter: 'drop-shadow(0 0 6px rgba(99,102,241,0.8)) drop-shadow(0 0 12px rgba(99,102,241,0.4))'
                                }}
                            />
                        </svg>
                    </div>

                    <Link href="#features" className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors">
                        Features
                    </Link>
                    <Link href="#platform" className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors">
                        Platform
                    </Link>
                    <Link href="#enterprise" className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors">
                        Enterprise
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
                        className="md:hidden mt-4 rounded-2xl bg-white/95 dark:bg-black/95 backdrop-blur-xl border border-gray-200/40 dark:border-white/10 shadow-xl overflow-visible"
                    >
                        <div className="px-4 py-4 space-y-2">
                            <Link href="#features" onClick={() => setIsOpen(false)} className="block px-4 py-3 rounded-xl text-base font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
                                Features
                            </Link>
                            <Link href="#platform" onClick={() => setIsOpen(false)} className="block px-4 py-3 rounded-xl text-base font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
                                Platform
                            </Link>
                            <Link href="#enterprise" onClick={() => setIsOpen(false)} className="block px-4 py-3 rounded-xl text-base font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
                                Enterprise
                            </Link>
                            <div className="pt-2">
                                <Link href="/search" onClick={() => setIsOpen(false)} className="flex items-center justify-center px-4 py-4 sm:hidden bg-gray-900 dark:bg-white text-white dark:text-black rounded-xl text-base font-bold shadow-md">
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
