import { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
    return {
        rules: {
            userAgent: "*",
            allow: "/",
            disallow: ["/api/", "/dataset/preview/"], // Wait I shouldn't guess, let's just make it basic
        },
        sitemap: "https://ranqora.ai/sitemap.xml",
    };
}
