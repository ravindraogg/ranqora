import { NextRequest } from "next/server";

/**
 * Serverless Proxy Route
 * Forwards requests from Vercel to a private HuggingFace Space.
 * This protects the HF_TOKEN and avoids CORS issues for private spaces.
 */

async function proxyRequest(req: NextRequest, context: any) {
    // Wait for params to be available (App Router requirement)
    const params = await context.params;
    const pathParts = params.path || [];
    const path = pathParts.join("/");

    const searchParams = req.nextUrl.searchParams.toString();
    const baseUrl = process.env.NEXT_HF_SPACE_URL;
    const token = process.env.NEXT_HF_TOKEN;

    if (!baseUrl) {
        return new Response(JSON.stringify({ error: "NEXT_HF_SPACE_URL environment variable is not set" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
        });
    }

    // Build the target URL, ensuring no double slashes
    const cleanBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
    const targetUrl = `${cleanBase}/${path}${searchParams ? `?${searchParams}` : ""}`;

    console.log(`[Proxy] ${req.method} ${req.nextUrl.pathname} -> ${targetUrl}`);

    // Prepare headers
    const headers = new Headers(req.headers);
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }

    // Security: Remove browser-specific headers that fetch will re-populate
    headers.delete("host");
    headers.delete("connection");
    headers.delete("content-length");

    try {
        let body: any = null;
        if (req.method !== "GET" && req.method !== "HEAD") {
            // Use arrayBuffer for the body to ensure all data types (JSON, binary) are handled
            body = await req.arrayBuffer();
        }

        const response = await fetch(targetUrl, {
            method: req.method,
            headers,
            body,
            // @ts-ignore - duplex is required for streaming bodies in some environments
            duplex: body ? "half" : undefined,
        });

        // Mirror the response back, including streaming support for SSE
        const responseHeaders = new Headers(response.headers);

        // Ensure we don't return forbidden headers
        responseHeaders.delete("content-encoding"); // Let Vercel handle compression
        responseHeaders.delete("transfer-encoding");

        return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: responseHeaders,
        });
    } catch (error: any) {
        console.error(`[Proxy Error] ${error.message}`);
        return new Response(JSON.stringify({ error: "Failed to fetch from backend", details: error.message }), {
            status: 502,
            headers: { "Content-Type": "application/json" },
        });
    }
}

export async function GET(req: NextRequest, context: any) {
    return proxyRequest(req, context);
}

export async function POST(req: NextRequest, context: any) {
    return proxyRequest(req, context);
}

export async function PUT(req: NextRequest, context: any) {
    return proxyRequest(req, context);
}

export async function DELETE(req: NextRequest, context: any) {
    return proxyRequest(req, context);
}

export async function PATCH(req: NextRequest, context: any) {
    return proxyRequest(req, context);
}

export const dynamic = "force-dynamic";
export const maxDuration = 60; // Extend timeout for long-running AI searches if on Pro
