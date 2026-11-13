/**
 * Cloudflare Worker — edge gateway SIDEWA.
 *
 * Tugasnya hanya meneruskan request ke origin FastAPI, bukan menjalankan
 * Python. Worker berguna untuk:
 *  - domain/route tambahan (mis. sidewa.riau.ai) tanpa membuka Colab;
 *  - cache aset /static/* di edge;
 *  - header keamanan dan endpoint diagnostik /__edge/*;
 *  - merapikan redirect absolut milik origin agar tetap di domain edge.
 */

const DEFAULT_ORIGIN = "https://dprd.riau.ai";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
]);

const STATIC_PREFIX = "/static/";
const STATIC_TTL_SECONDS = 300;

function resolveOrigin(env) {
  const raw = (env && env.ORIGIN) || DEFAULT_ORIGIN;
  try {
    return new URL(raw);
  } catch {
    return new URL(DEFAULT_ORIGIN);
  }
}

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extraHeaders,
    },
  });
}

function buildTarget(requestUrl, origin) {
  const target = new URL(origin.origin);
  target.pathname = requestUrl.pathname;
  target.search = requestUrl.search;
  return target;
}

function forwardHeaders(request, origin, edgeHost) {
  const headers = new Headers(request.headers);
  for (const name of HOP_BY_HOP) {
    headers.delete(name);
  }

  const clientIp = request.headers.get("CF-Connecting-IP");
  if (clientIp) {
    headers.set("X-Forwarded-For", clientIp);
    headers.set("X-Real-IP", clientIp);
  }
  headers.set("X-Forwarded-Host", edgeHost);
  headers.set("X-Forwarded-Proto", "https");
  headers.set("X-SIDEWA-Edge", "cloudflare-worker");

  // Origin yang dilindungi Basic Auth (opsional).
  if (origin.username) {
    const credentials = `${decodeURIComponent(origin.username)}:${decodeURIComponent(
      origin.password,
    )}`;
    headers.set("Authorization", `Basic ${btoa(credentials)}`);
  }
  return headers;
}

function rewriteRedirect(response, origin) {
  const location = response.headers.get("Location");
  if (!location) {
    return response;
  }
  try {
    const resolved = new URL(location, origin);
    if (resolved.origin !== origin.origin) {
      return response;
    }
    const headers = new Headers(response.headers);
    headers.set("Location", `${resolved.pathname}${resolved.search}${resolved.hash}`);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  } catch {
    return response;
  }
}

async function fetchOrigin(request, env, edgeHost) {
  const origin = resolveOrigin(env);
  const target = buildTarget(new URL(request.url), origin);
  const init = {
    method: request.method,
    headers: forwardHeaders(request, origin, edgeHost),
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  let response;
  try {
    response = await fetch(target, init);
  } catch (error) {
    console.error("origin fetch gagal", target.toString(), error);
    return json(
      {
        detail: "Origin SIDEWA tidak dapat dijangkau dari edge.",
        origin: origin.origin,
      },
      502,
      { "x-sidewa-edge": "cloudflare-worker" },
    );
  }

  const headers = new Headers(response.headers);
  for (const name of HOP_BY_HOP) {
    headers.delete(name);
  }
  headers.set("X-SIDEWA-Edge", "cloudflare-worker");
  headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");

  return rewriteRedirect(
    new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    }),
    origin,
  );
}

async function serveStatic(request, env, ctx, edgeHost) {
  if (request.method !== "GET") {
    return null;
  }
  const url = new URL(request.url);
  if (!url.pathname.startsWith(STATIC_PREFIX)) {
    return null;
  }

  const cache = caches.default;
  const cacheKey = new Request(url.toString(), { method: "GET" });
  const cached = await cache.match(cacheKey);
  if (cached) {
    const hit = new Response(cached.body, cached);
    hit.headers.set("X-Edge-Cache", "HIT");
    return hit;
  }

  const response = await fetchOrigin(request, env, edgeHost);
  if (!response.ok) {
    return response;
  }

  const headers = new Headers(response.headers);
  headers.set("Cache-Control", `public, max-age=${STATIC_TTL_SECONDS}`);
  headers.set("X-Edge-Cache", "MISS");
  const cacheable = new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
  ctx.waitUntil(cache.put(cacheKey, cacheable.clone()));
  return cacheable;
}

async function handleEdgeEndpoint(url, env) {
  const origin = resolveOrigin(env);
  if (url.pathname === "/__edge/health") {
    return json({
      status: "ok",
      service: "sidewa-edge",
      runtime: "cloudflare-worker",
      origin: origin.origin,
    });
  }
  if (url.pathname === "/__edge/ready") {
    try {
      const response = await fetch(new URL("/readyz", origin), {
        headers: {
          "user-agent": "Mozilla/5.0 (compatible; SIDEWA-Edge/1.0)",
          accept: "application/json",
        },
        redirect: "manual",
      });
      const body = await response.text();
      return new Response(body, {
        status: response.status,
        headers: {
          "content-type": response.headers.get("content-type") || "application/json",
          "cache-control": "no-store",
          "x-sidewa-edge": "cloudflare-worker",
        },
      });
    } catch (error) {
      return json(
        { status: "degraded", origin: origin.origin, error: String(error) },
        503,
      );
    }
  }
  return null;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const edgeEndpoint = await handleEdgeEndpoint(url, env);
    if (edgeEndpoint) {
      return edgeEndpoint;
    }

    const cached = await serveStatic(request, env, ctx, url.host);
    if (cached) {
      return cached;
    }

    return fetchOrigin(request, env, url.host);
  },
};
