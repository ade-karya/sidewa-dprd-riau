/**
 * Cloudflare Pages Function — proxy penuh SIDEWA.
 *
 * Semua request (kecuali aset statis yang ada di folder public/) diteruskan
 * ke origin FastAPI. Dengan cara ini aplikasi bisa dibuka dari
 * https://<project>.pages.dev tanpa memindahkan backend Python ke Workers.
 *
 * Variabel lingkungan:
 *   ORIGIN  URL origin, default https://dprd.riau.ai
 *
 * Batas praktis Cloudflare Pages Functions:
 *   - tidak menjalankan Python/FastAPI/dlib (hanya JavaScript/Workers runtime);
 *   - request body maksimum 100 MB (unggah SIDEWA dibatasi 15 MB/foto);
 *   - kuota gratis 100.000 request/hari.
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

function resolveOrigin(env) {
  const raw = (env && env.ORIGIN) || DEFAULT_ORIGIN;
  try {
    return new URL(raw);
  } catch {
    return new URL(DEFAULT_ORIGIN);
  }
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-sidewa-edge": "cloudflare-pages",
    },
  });
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
  headers.set("X-SIDEWA-Edge", "cloudflare-pages");

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

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const origin = resolveOrigin(env);

  if (url.pathname === "/__edge/health") {
    return json({
      status: "ok",
      service: "sidewa-pages",
      runtime: "cloudflare-pages",
      origin: origin.origin,
    });
  }

  if (url.pathname === "/__edge/ready") {
    try {
      const response = await fetch(new URL("/readyz", origin), {
        headers: {
          "user-agent": "Mozilla/5.0 (compatible; SIDEWA-Pages/1.0)",
          accept: "application/json",
        },
        redirect: "manual",
      });
      return new Response(await response.text(), {
        status: response.status,
        headers: {
          "content-type": response.headers.get("content-type") || "application/json",
          "cache-control": "no-store",
          "x-sidewa-edge": "cloudflare-pages",
        },
      });
    } catch (error) {
      return json({ status: "degraded", origin: origin.origin, error: String(error) }, 503);
    }
  }

  const target = new URL(origin.origin);
  target.pathname = url.pathname;
  target.search = url.search;

  const init = {
    method: request.method,
    headers: forwardHeaders(request, origin, url.host),
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
      { detail: "Origin SIDEWA tidak dapat dijangkau dari edge.", origin: origin.origin },
      502,
    );
  }

  const headers = new Headers(response.headers);
  for (const name of HOP_BY_HOP) {
    headers.delete(name);
  }
  headers.set("X-SIDEWA-Edge", "cloudflare-pages");
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
