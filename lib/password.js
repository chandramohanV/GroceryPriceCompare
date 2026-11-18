// Shared by the Pages Functions in functions/api/: checks the upload password.

async function sha256(text) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

// Compares hashes in constant time so the password can't be guessed by timing.
export async function hasUploadPassword(request, env) {
  if (!env.UPLOAD_PASSWORD) return false;
  const given = (request.headers.get("Authorization") || "").replace(/^Bearer /, "");
  const [a, b] = await Promise.all([sha256(given), sha256(env.UPLOAD_PASSWORD)]);
  return crypto.subtle.timingSafeEqual(a, b);
}

export function reply(status, message) {
  return new Response(JSON.stringify({ message }), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
