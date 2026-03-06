import { NextRequest } from "next/server";

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(req, params);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(req, params);
}

async function proxyRequest(req: NextRequest, paramsPromise: Promise<{ path: string[] }>) {
    const { path: pathParts } = await paramsPromise;
    const path = (pathParts || []).join("/");

    const baseUrl = process.env.NEXT_HF_SPACE_URL;
    const token = process.env.NEXT_HF_TOKEN;

    if (!baseUrl) {
        return new Response(JSON.stringify({ error: "NEXT_HF_SPACE_URL not set" }), { status: 500 });
    }

    const cleanBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
    const searchParams = req.nextUrl.searchParams.toString();
    const targetUrl = `${cleanBase}/${path}${searchParams ? `?${searchParams}` : ""}`;

    const headers = new Headers(req.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    headers.delete("host");

    try {
        const body = (req.method !== "GET" && req.method !== "HEAD") ? await req.arrayBuffer() : null;
        const response = await fetch(targetUrl, {
            method: req.method,
            headers,
            body,
            // @ts-ignore
            duplex: body ? "half" : undefined,
        });

        return new Response(response.body, {
            status: response.status,
            headers: response.headers,
        });
    } catch (error: any) {
        return new Response(JSON.stringify({ error: error.message }), { status: 502 });
    }
}
