import { Hexagon } from 'lucide-react';
import Link from 'next/link';

export function Footer() {
    return (
        <footer className="bg-white dark:bg-black border-t border-gray-200 dark:border-white/10">
            <div className="mx-auto max-w-7xl px-6 py-12 lg:px-8">
                <div className="md:flex md:items-center md:justify-between">
                    <div className="flex justify-center md:justify-start items-center gap-2 mb-6 md:mb-0">
                        <Hexagon className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                        <span className="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Ranqora</span>
                    </div>
                    <p className="text-center text-sm leading-5 text-gray-500 dark:text-gray-400">
                        &copy; {new Date().getFullYear()} Ranqora Platform, Inc. All rights reserved.
                    </p>
                </div>
            </div>
        </footer>
    );
}
