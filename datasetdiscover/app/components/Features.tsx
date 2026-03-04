'use client';

import { motion } from 'framer-motion';
import { Database, Filter, BrainCircuit, ShieldCheck, Zap, Sparkles } from 'lucide-react';

const features = [
    {
        name: 'Unified Data Discovery',
        description: 'Fetch datasets from Kaggle, HuggingFace, and internal silos instantly with our multi-source orchestration engine.',
        icon: Database,
    },
    {
        name: 'LLM Query Parsing',
        description: 'Use natural language. Ranqora automatically infers domains and extracts deep technical requirements via Gemini.',
        icon: BrainCircuit,
    },
    {
        name: 'Multi-Factor Ranking',
        description: 'Datasets are ranked by semantic relevance, task alignment, quality scores, open-source licensing, and freshness.',
        icon: Filter,
    },
    {
        name: 'Enterprise Security',
        description: 'Role-based access control, secure proxy downloads, and graph-based citation tracking keep compliance simple.',
        icon: ShieldCheck,
    },
    {
        name: 'Auto-Preparation Layer',
        description: 'Preview multi-GB files instantly. Our 1MB edge limit protects your bandwidth while delivering structural data instantly.',
        icon: Zap,
    },
    {
        name: 'Feedback Learning',
        description: 'A LightGBM LambdaRank engine that learns dataset relevance from your teams clicks and downloads.',
        icon: Sparkles,
    },
];

export function Features() {
    return (
        <div className="py-24 bg-gray-50 dark:bg-zinc-950 sm:py-32" id="features">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="mx-auto max-w-2xl lg:text-center">
                    <h2 className="text-base font-semibold leading-7 text-indigo-600 dark:text-indigo-400">Discover Faster</h2>
                    <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl">
                        Everything you need to train models
                    </p>
                    <p className="mt-6 text-lg leading-8 text-gray-600 dark:text-gray-300">
                        Ranqora acts as the intelligent orchestration layer between messy raw data and your pristine machine learning pipelines.
                    </p>
                </div>
                <div className="mx-auto mt-16 max-w-2xl sm:mt-20 lg:mt-24 lg:max-w-none">
                    <dl className="grid max-w-xl grid-cols-1 gap-x-8 gap-y-16 lg:max-w-none lg:grid-cols-3">
                        {features.map((feature, idx) => (
                            <motion.div
                                key={feature.name}
                                className="flex flex-col"
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ duration: 0.5, delay: idx * 0.1 }}
                            >
                                <dt className="flex items-center gap-x-3 text-base font-semibold leading-7 text-gray-900 dark:text-white">
                                    <div className="h-10 w-10 flex items-center justify-center rounded-lg bg-indigo-600 dark:bg-indigo-500/10">
                                        <feature.icon className="h-6 w-6 text-white dark:text-indigo-400" aria-hidden="true" />
                                    </div>
                                    {feature.name}
                                </dt>
                                <dd className="mt-4 flex flex-auto flex-col text-base leading-7 text-gray-600 dark:text-gray-400">
                                    <p className="flex-auto">{feature.description}</p>
                                </dd>
                            </motion.div>
                        ))}
                    </dl>
                </div>
            </div>
        </div>
    );
}
