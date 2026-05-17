import Link from "next/link";

export default function NotFound() {
    return (
        <div className="min-h-screen bg-white dark:bg-black text-black dark:text-white flex flex-col items-center justify-center p-4">
            <div className="max-w-md w-full text-center space-y-6">
                <h2 className="text-8xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-purple-600">
                    404
                </h2>
                <h3 className="text-2xl font-bold">Page Not Found</h3>
                <p className="text-gray-600 dark:text-gray-400">
                    We could not find the page you were looking for. The dataset or resource may have been moved or doesn't exist.
                </p>
                <div className="pt-6">
                    <Link
                        href="/"
                        className="px-8 py-3 bg-black dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-200 rounded-full font-semibold transition-all shadow-md hover:shadow-lg inline-flex items-center gap-2"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                        Back to Discovery
                    </Link>
                </div>
            </div>
        </div>
    );
}
