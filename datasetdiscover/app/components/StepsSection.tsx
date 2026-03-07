'use client';

import { motion } from 'framer-motion';
import { Search, BrainCircuit, Database, BarChart2, FileCheck, Share2, Shield } from 'lucide-react';

const steps = [
    {
        title: 'Query Decomposition',
        desc: 'Gemini LLM parses your natural language into technical search parameters and domain constraints.',
        icon: Search
    },
    {
        title: 'Global Retrieval',
        desc: 'Parallel orchestration across ArXiv, Kaggle, IEEE, and more to gather a wide candidate base.',
        icon: Database
    },
    {
        title: 'Graph Intelligence',
        desc: 'Candidates are ingested into a knowledge graph to analyze citations and paper-dataset relationships.',
        icon: BrainCircuit
    },
    {
        title: 'Rank Scoring',
        desc: 'LightGBM LambdaRank models score relevance using 20+ factors including freshness and quality.',
        icon: BarChart2
    },
    {
        title: 'Metadata Enrichment',
        desc: 'Datasets are auto-prepared with structural previews and metadata extracted from original research.',
        icon: FileCheck
    },
    {
        title: 'Verification & Integrity',
        desc: 'Final integrity checks ensure data modality, size, and annotation quality meet elite standards.',
        icon: Shield
    },
    {
        title: 'Insight Delivery',
        desc: 'A definitive ranked list is delivered, categorized into practical and research benchmarks.',
        icon: Share2
    }
];

export function StepsSection() {
    return (
        <section id="steps" className="py-24 bg-gray-50 dark:bg-zinc-950">
            <div className="max-w-7xl mx-auto px-6 lg:px-8">
                <div className="flex flex-col md:flex-row md:items-end justify-between mb-16 gap-6">
                    <div className="max-w-2xl text-left">
                        <h2 className="text-base font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-widest">How it Works</h2>
                        <p className="mt-2 text-4xl font-black text-gray-900 dark:text-white tracking-tight leading-tight">7 Layers of Discovery</p>
                    </div>
                    <p className="max-w-xs text-sm text-gray-500 dark:text-gray-400">
                        Our autonomous agent follows a rigorous scientific pipeline to ensure zero-loss discovery.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {steps.map((step, idx) => (
                        <motion.div
                            key={step.title}
                            initial={{ opacity: 0, scale: 0.95 }}
                            whileInView={{ opacity: 1, scale: 1 }}
                            whileHover={{ rotate: 10 }}
                            viewport={{ once: true }}
                            transition={{ delay: idx * 0.1 }}
                            className="relative p-8 rounded-[2.5rem] bg-white dark:bg-black border border-gray-200 dark:border-white/5 shadow-sm group hover:border-indigo-500/30 transition-all cursor-pointer"
                        >
                            <div className="absolute top-8 right-8 text-4xl font-black text-[#4F39F6] opacity-60 transition-colors">
                                0{idx + 1}
                            </div>
                            <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center text-indigo-600 mb-6 group-hover:bg-indigo-600 group-hover:text-white transition-all">
                                <step.icon className="w-6 h-6" />
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-3">{step.title}</h3>
                            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{step.desc}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
