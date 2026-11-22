// Cloudflare Pages Function at /api/run: the site's "Run now" button.
//
// POST (with "Authorization: Bearer <UPLOAD_PASSWORD>") starts the GitHub
// Actions workflow that scrapes Lidl and Aldi and saves the merged offers back to
// /api/offers. The same workflow also runs by itself every Monday.
//
// Needs the GITHUB_TOKEN secret: a fine-grained token for this repository
// with "Actions: read and write". GITHUB_REPO and WORKFLOW come from wrangler.toml.
import { hasUploadPassword, reply } from "../../lib/password.js";

const GITHUB_API = "https://api.github.com";
const BRANCH = "main";

export async function onRequestPost({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  if (!env.GITHUB_TOKEN) return reply(501, "The Run button isn't set up yet (GITHUB_TOKEN is missing)");

  const url = `${GITHUB_API}/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "GroceryPriceCompare",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: BRANCH }),
  });
  if (!resp.ok) return reply(502, `GitHub refused to start the run (HTTP ${resp.status})`);
  return reply(202, "Started");
}
