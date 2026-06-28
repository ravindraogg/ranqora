'use client';

import { useState, useLayoutEffect } from 'react';
import Link from 'next/link';
import { Menu, X, Hexagon, Moon, Sun, Database, Zap, FileText, Brain, Globe, Code, Shield, CheckCircle2, Search } from 'lucide-react';
import { motion, AnimatePresence, useScroll, useSpring, useTransform } from 'framer-motion';
import { useTheme } from 'next-themes';
import { cn } from '../lib/utils';



const tools = [
    { name: 'Kaggle', icon: Database, color: 'text-blue-500', bgColor: 'bg-blue-500/10', href: '#tools' },
    { name: 'HuggingFace', icon: Zap, color: 'text-yellow-500', bgColor: 'bg-yellow-500/10', href: '#tools' },
    { name: 'ArXiv', icon: FileText, color: 'text-red-500', bgColor: 'bg-red-500/10', href: '#tools' },
    { name: 'IEEE Xplore', icon: Shield, color: 'text-indigo-500', bgColor: 'bg-indigo-500/10', href: '#tools' },
    { name: 'Semantic Scholar', icon: Brain, color: 'text-cyan-500', bgColor: 'bg-cyan-500/10', href: '#tools' },
    { name: 'OpenDataPortal', icon: Globe, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10', href: '#tools' },
    { name: 'GitHub', icon: Code, color: 'text-gray-500', bgColor: 'bg-gray-500/10', href: '#tools' },
];

export function Navbar() {
    const [isOpen, setIsOpen] = useState(false);

    const { theme, setTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    const { scrollY } = useScroll();
    const scrollSpring = useSpring(scrollY, { stiffness: 400, damping: 90 });

    // Transform values for a "shrinking" and "glass" effect on scroll
    const navScale = useTransform(scrollSpring, [0, 100], [1, 0.98]);
    const navOpacity = useTransform(scrollSpring, [0, 100], [1, 0.95]);

    useLayoutEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setMounted(true);
    }, []);

    if (!mounted) return null;

    return (
        <motion.nav
            style={{ scale: navScale, opacity: navOpacity }}
            className="fixed top-6 left-0 right-0 z-50 flex justify-center px-4"
        >
            <div className="w-full max-w-5xl flex items-center justify-between gap-2 md:gap-4 p-1">

                {/* Section 1: Brand Logo */}
                <motion.div
                    initial={{ x: -20, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    className="h-14 px-5 flex items-center gap-3 rounded-full border border-gray-200/40 dark:border-white/5 bg-white/70 dark:bg-black/70 backdrop-blur-xl shadow-lg shrink-0"
                >
                    <Link href="/" className="flex items-center gap-2 group">
                        <div className="relative">
                            <Hexagon className="w-6 h-6 text-indigo-600 dark:text-indigo-400 group-hover:rotate-12 transition-transform duration-300" />
                            <div className="absolute inset-0 bg-indigo-500/20 blur-lg rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <span className="font-bold text-lg tracking-tight text-gray-900 dark:text-white">
                            Ranqora
                        </span>
                    </Link>
                </motion.div>

                {/* Section 2: Core Navigation */}
                <motion.div
                    initial={{ y: -20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    className="hidden md:flex flex-1 h-14 items-center justify-center gap-8 rounded-full border border-gray-200/40 dark:border-white/5 bg-white/70 dark:bg-black/70 backdrop-blur-xl shadow-lg px-8 relative overflow-hidden"
                >
                    <Link href="#features" className="text-sm font-semibold text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-white transition-all">
                        Features
                    </Link>

                    <Link href="#tools" className="text-sm font-semibold text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-white transition-all">
                        Tools
                    </Link>



                    <Link href="#steps" className="flex items-center gap-1.5 text-sm font-semibold text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-white transition-all">
                        <CheckCircle2 className="w-4 h-4 text-indigo-500" />
                        Steps
                    </Link>
                </motion.div>

                {/* Section 3: Utilities & Action */}
                <motion.div
                    initial={{ x: 20, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    className="flex items-center gap-2"
                >
                    <button
                        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        className="h-14 w-14 flex items-center justify-center rounded-full border border-gray-200/40 dark:border-white/5 bg-white/70 dark:bg-black/70 backdrop-blur-xl shadow-lg transition-all hover:scale-105 active:scale-95 text-gray-600 dark:text-gray-300"
                    >
                        {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
                    </button>

                    <Link
                        href="/search"
                        className="hidden sm:flex h-14 px-8 items-center justify-center rounded-full bg-gray-900 text-white dark:bg-white dark:text-black text-sm font-bold transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg gap-2 group"
                    >
                        <Search className="w-4 h-4 group-hover:rotate-12 transition-transform" />
                        Get Started
                    </Link>

                    <button
                        onClick={() => setIsOpen(!isOpen)}
                        className="md:hidden h-14 w-14 flex items-center justify-center rounded-full border border-gray-200/40 dark:border-white/5 bg-white/70 dark:bg-black/70 backdrop-blur-xl shadow-lg text-gray-600 dark:text-gray-300"
                    >
                        {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                    </button>
                </motion.div>

            </div>

            {/* Mobile Navigation Mesh Overlay */}
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.98, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.98, y: 10 }}
                        className="absolute top-24 left-4 right-4 p-6 rounded-[2.5rem] bg-white/95 dark:bg-zinc-950/95 backdrop-blur-3xl border border-gray-200/40 dark:border-white/5 shadow-2xl md:hidden z-10"
                    >
                        <div className="space-y-6">
                            <div className="grid grid-cols-1 gap-2">
                                <MobileNavItem href="#features" icon={Hexagon} label="Features" onClick={() => setIsOpen(false)} />
                                <MobileNavItem href="#steps" icon={CheckCircle2} label="Steps" onClick={() => setIsOpen(false)} />
                            </div>

                            <div className="pt-4 space-y-4">
                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.2em] px-4">Cloud Integrations</p>
                                <div className="grid grid-cols-2 gap-2">
                                    {tools.slice(0, 4).map((tool) => (
                                        <Link key={tool.name} href={tool.href} onClick={() => setIsOpen(false)} className="flex items-center gap-3 p-3 rounded-2xl bg-gray-50 dark:bg-white/5">
                                            <tool.icon className={cn("w-4 h-4", tool.color)} />
                                            <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{tool.name}</span>
                                        </Link>
                                    ))}
                                </div>
                            </div>



                            <Link
                                href="/search"
                                onClick={() => setIsOpen(false)}
                                className="flex items-center justify-center h-16 w-full bg-gray-900 dark:bg-white text-white dark:text-black rounded-3xl font-bold text-lg shadow-xl"
                            >
                                Launch Platform
                            </Link>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.nav>
    );
}

interface MobileNavItemProps {
    href: string;
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    onClick: () => void;
}

function MobileNavItem({ href, icon: Icon, label, onClick }: MobileNavItemProps) {
    return (
        <Link
            href={href}
            onClick={onClick}
            className="flex items-center gap-4 px-5 py-4 rounded-2xl bg-gray-50 dark:bg-white/5 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
        >
            <div className="p-2 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-white/10">
                <Icon className="w-5 h-5 text-indigo-500" />
            </div>
            <span className="text-base font-bold text-gray-900 dark:text-gray-100">{label}</span>
        </Link>
    );
}
