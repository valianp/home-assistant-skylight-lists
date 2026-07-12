#!/usr/bin/env node
/**
 * Creates a Skylight Lists entry through Home Assistant's supported
 * configuration-flow REST API. It does not automate a browser or edit .storage.
 *
 * Required environment variables: HA_URL, HA_TOKEN, SKYLIGHT_USERNAME,
 * SKYLIGHT_PASSWORD, and SKYLIGHT_FRAME_ID.
 */

const required = ["HA_URL", "HA_TOKEN", "SKYLIGHT_USERNAME", "SKYLIGHT_PASSWORD", "SKYLIGHT_FRAME_ID"];
const missing = required.filter((name) => !process.env[name]);
if (missing.length) {
  console.error(`Missing environment variables: ${missing.join(", ")}`);
  process.exit(2);
}

const baseUrl = process.env.HA_URL.replace(/\/$/, "");
const headers = {
  Authorization: `Bearer ${process.env.HA_TOKEN}`,
  "Content-Type": "application/json",
};

async function request(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.message ?? `Home Assistant returned HTTP ${response.status}`);
  return result;
}

try {
  const flow = await request("/api/config/config_entries/flow", { handler: "skylight_lists" });
  const result = await request(`/api/config/config_entries/flow/${flow.flow_id}`, {
    username: process.env.SKYLIGHT_USERNAME,
    password: process.env.SKYLIGHT_PASSWORD,
    frame_id: process.env.SKYLIGHT_FRAME_ID,
  });
  if (result.type !== "create_entry") {
    throw new Error(`Config flow did not create an entry: ${JSON.stringify(result)}`);
  }
  console.log("Skylight Lists was configured successfully.");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
