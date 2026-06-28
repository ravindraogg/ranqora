'use client';

import { motion } from 'framer-motion';
import { Database, FileText, Brain, Globe, Code, Zap, Shield } from 'lucide-react';

const tools = [
    { name: 'Kaggle', icon: Database, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { name: 'HuggingFace', icon: Zap, color: 'text-yellow-500', bg: 'bg-yellow-500/10' },
    { name: 'ArXiv', icon: FileText, color: 'text-red-500', bg: 'bg-red-500/10' },
    { name: 'IEEE Xplore', icon: Shield, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
    { name: 'Semantic Scholar', icon: Brain, color: 'text-cyan-500', bg: 'bg-cyan-500/10' },
    { name: 'OpenDataPortal', icon: Globe, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { name: 'GitHub', icon: Code, color: 'text-gray-500', bg: 'bg-gray-500/10' },
];

export function ToolsSection() {
    return (
        <section id="tools" className="py-24 bg-white dark:bg-black overflow-hidden">
            <div className="max-w-7xl mx-auto px-6 lg:px-8">
                <div className="text-center mb-16">
                    <h2 className="text-base font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-widest">Our Ecosystem</h2>
                    <p className="mt-2 text-4xl font-black text-gray-900 dark:text-white tracking-tight">Connected Data Intelligence</p>
                    <p className="mt-4 text-lg text-gray-600 dark:text-gray-400">Ranqora orchestrates across the world&apos;s leading data and research platforms.</p>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 md:grid-cols-3 gap-6">
                    {tools.map((tool, idx) => (
                        <motion.div
                            key={tool.name}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: idx * 0.1 }}
                            whileHover={{ rotate: 10 }}
                            className="p-6 rounded-[2rem] border border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-zinc-900/50 flex flex-col items-center text-center gap-4 transition-all hover:shadow-xl hover:shadow-indigo-500/5 hover:border-indigo-500/20 cursor-pointer"
                        >
                            <div className={`w-12 h-12 rounded-2xl ${tool.bg} flex items-center justify-center ${tool.color}`}>
                                <tool.icon className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-bold text-gray-900 dark:text-white">{tool.name}</h3>
                                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold mt-1">Verified Source</p>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
