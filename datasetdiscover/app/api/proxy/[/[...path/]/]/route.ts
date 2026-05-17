import { NextRequest } from "next/server";

// Next.js 15 strict context typing for optional catch-all route at app/api/proxy/[[...path]]
type Context = {
    params: Promise<{
        path?: string[];
    }>;
};

async function proxyRequest(req: NextRequest, { params }: Context) {
    // Resolve the dynamic path segment
    const resolvedParams = await params;
    const pathParts = resolvedParams.path || [];
    const path = pathParts.join("/");

    const baseUrl = process.env.NEXT_HF_SPACE_URL;
    const token = process.env.NEXT_HF_TOKEN;

    if (!baseUrl) {
        return new Response(JSON.stringify({ error: "NEXT_HF_SPACE_URL is not set" }), {
            status: 500,
            headers: { "Content-Type": "application/json" }
        });
    }

    // Ensure target URL is correct
    const cleanBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
    const searchParams = req.nextUrl.searchParams.toString();
    const targetUrl = `${cleanBase}/${path}${searchParams ? `?${searchParams}` : ""}`;

    console.log(`[Proxy] ${req.method} ${targetUrl}`);

    // Forward headers, but clean browser/Vercel ones
    const headers = new Headers(req.headers);
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    headers.delete("host");
    headers.delete("connection");

    try {
        let body: any = null;
        if (req.method !== "GET" && req.method !== "HEAD") {
            body = await req.arrayBuffer();
        }

        const response = await fetch(targetUrl, {
            method: req.method,
            headers,
            body,
            // @ts-ignore - duplex is needed for streaming support in some environments
            duplex: body ? "half" : undefined,
        });

        const responseHeaders = new Headers(response.headers);
        responseHeaders.delete("content-encoding");
        responseHeaders.delete("transfer-encoding");

        return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: responseHeaders,
        });
    } catch (error: any) {
        console.error(`[Proxy Error] ${error.message}`);
        return new Response(JSON.stringify({ error: "Proxy connection failed", details: error.message }), {
            status: 502,
            headers: { "Content-Type": "application/json" }
        });
    }
}

export async function GET(req: NextRequest, context: Context) {
    return proxyRequest(req, context);
}

export async function POST(req: NextRequest, context: Context) {
    return proxyRequest(req, context);
}

export async function PUT(req: NextRequest, context: Context) {
    return proxyRequest(req, context);
}

export async function DELETE(req: NextRequest, context: Context) {
    return proxyRequest(req, context);
}

export const dynamic = "force-dynamic";
export const maxDuration = 60;
