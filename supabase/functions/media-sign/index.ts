// Supabase Edge Function: media-sign
// Returns short-lived presigned GET URLs for the private HF S3 media bucket.
// The S3 secret stays in Supabase secrets; the Android APK never receives it.
import { AwsClient } from "npm:aws4fetch@1.0.20";

const endpoint = (Deno.env.get("HF_S3_ENDPOINT") ?? "").replace(/\/+$/, "");
const bucket = Deno.env.get("HF_S3_BUCKET") ?? "";
const accessKeyId = Deno.env.get("HF_S3_ACCESS_KEY_ID") ?? "";
const secretAccessKey = Deno.env.get("HF_S3_SECRET_ACCESS_KEY") ?? "";
const region = Deno.env.get("HF_S3_REGION") || "us-east-1";

const client = new AwsClient({ accessKeyId, secretAccessKey, service: "s3", region });

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function reply(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
  });
}

// Only media prefixes used by DewanKu; block traversal and absolute keys.
const PREFIXES = ["members/", "activities/", "press/", "humas/", "drive/", "media/"];

function isValidKey(key: unknown): key is string {
  return (
    typeof key === "string" &&
    key.length > 0 &&
    key.length <= 512 &&
    PREFIXES.some((prefix) => key.startsWith(prefix)) &&
    !key.includes("..") &&
    !key.includes("\\") &&
    !key.startsWith("/")
  );
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return reply({ error: "method not allowed" }, 405);
  if (!endpoint || !bucket || !accessKeyId || !secretAccessKey) {
    return reply({ error: "media signer is not configured" }, 500);
  }

  let body: { keys?: unknown; expires?: unknown };
  try {
    body = await req.json();
  } catch {
    return reply({ error: "invalid json" }, 400);
  }

  const keys = Array.isArray(body.keys) ? body.keys.slice(0, 80) : [];
  const requested = Number(body.expires);
  const expires = Number.isFinite(requested)
    ? Math.min(Math.max(Math.trunc(requested), 60), 86400)
    : 3600;

  const urls: Record<string, string> = {};
  await Promise.all(
    keys.filter(isValidKey).map(async (key) => {
      const url = new URL(`${endpoint}/${bucket}/${key}`);
      url.searchParams.set("X-Amz-Expires", String(expires));
      const signed = await client.sign(url.toString(), {
        method: "GET",
        aws: { signQuery: true },
      });
      urls[key] = signed.url.toString();
    }),
  );

  return reply({ urls, expires });
});
