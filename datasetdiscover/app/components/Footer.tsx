import { Hexagon } from 'lucide-react';
import Link from 'next/link';

export function Footer() {
    return (
        <footer className="bg-white dark:bg-black border-t border-gray-100 dark:border-white/5">
            <div className="mx-auto max-w-7xl px-6 py-12 lg:px-8">
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 mb-12">
                    <div className="col-span-2">
                        <div className="flex items-center gap-2 mb-4">
                            <Hexagon className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                            <span className="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Ranqora</span>
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs leading-relaxed">
                            The intelligent orchestration layer for global dataset discovery and preparation.
                        </p>
                    </div>
                    <div>
                        <h4 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-widest mb-4">Platform</h4>
                        <ul className="space-y-2 text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors">
                            <li><Link href="#features">Features</Link></li>
                            <li><Link href="#tools">Integrations</Link></li>
                            <li><Link href="/topdatasets">Leaderboard</Link></li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-widest mb-4">Support</h4>
                        <ul className="space-y-2 text-sm text-gray-500">
                            <li><Link href="#" className="hover:text-indigo-500 transition-colors">Documentation</Link></li>
                            <li><Link href="#" className="hover:text-indigo-500 transition-colors">API Reference</Link></li>
                            <li><Link href="#" className="hover:text-indigo-500 transition-colors">Help Center</Link></li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-widest mb-4">Version</h4>
                        <div className="flex flex-col gap-2">
                            <span className="text-[10px] font-mono px-2 py-1 bg-gray-100 dark:bg-white/5 rounded border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 w-fit">
                                v1.1.4-agent
                            </span>
                            <span className="text-[10px] text-emerald-500 font-bold uppercase">System Stable</span>
                        </div>
                    </div>
                </div>
                <div className="pt-8 border-t border-gray-100 dark:border-white/5 flex flex-col md:flex-row justify-between items-center gap-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        &copy; {new Date().getFullYear()} Ranqora Platform, Inc. · Built for Enterprise Intelligence
                    </p>
                    <div className="flex gap-6 text-xs text-gray-500">
                        <Link href="#" className="hover:text-gray-900 dark:hover:text-white transition-colors">Privacy Policy</Link>
                        <Link href="#" className="hover:text-gray-900 dark:hover:text-white transition-colors">Terms of Service</Link>
                    </div>
                </div>
            </div>
        </footer>
    );
}
