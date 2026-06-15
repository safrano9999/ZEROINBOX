import { spawn } from "node:child_process";
import fs from "node:fs";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const pluginRoot = path.resolve(fileURLToPath(new URL(".", import.meta.url)));
const pluginConfigPath = path.join(pluginRoot, "config.conf");
const requirementsPath = path.join(pluginRoot, "requirements.txt");
const venvDir = path.join(pluginRoot, ".venv");
const venvPython = path.join(venvDir, "bin", "python");
const defaultWebhookPath = "/plugins/zeroinbox/run";

const configSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    configPath: {
      type: "string",
      description: "Optional path to ZEROINBOX config.conf.",
    },
    pythonPath: {
      type: "string",
      description: "Optional Python interpreter path.",
    },
    envFile: {
      type: "string",
      description: "Optional dotenv file with IMAP and LLM credentials.",
    },
    autoSetupPython: {
      type: "boolean",
      default: true,
      description: "Create a plugin .venv and install requirements on first use.",
    },
    defaultArgs: {
      type: "string",
      default: "sort --commit",
      description: "Arguments used when /zeroinbox is called without text.",
    },
    webhook: {
      type: "object",
      additionalProperties: false,
      properties: {
        enabled: { type: "boolean", default: true },
        path: { type: "string", default: defaultWebhookPath },
        args: { type: "string", default: "sort --commit" },
      },
    },
    delivery: {
      type: "object",
      additionalProperties: false,
      description: "Optional outbound destination used by the webhook.",
      properties: {
        channel: {
          type: "string",
          default: "telegram",
        },
        target: {
          type: "string",
          description: "Telegram chat id or another channel-specific destination.",
        },
        accountId: {
          type: "string",
          description: "Optional channel account id.",
        },
      },
    },
  },
};

const toolParameters = {
  type: "object",
  additionalProperties: true,
  properties: {
    raw: {
      type: "string",
      description: "Raw /zeroinbox arguments, for example 'sort --dry-run'.",
    },
  },
};

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function expandHome(raw) {
  if (!raw.startsWith("~/")) {
    return raw;
  }
  return path.join(process.env.HOME ?? process.cwd(), raw.slice(2));
}

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function readPluginConfig(ctx) {
  if (isRecord(ctx?.pluginConfig)) {
    return ctx.pluginConfig;
  }
  const config = ctx.getRuntimeConfig?.() ?? ctx.runtimeConfig ?? ctx.config;
  const entries = isRecord(config?.plugins) && isRecord(config.plugins.entries)
    ? config.plugins.entries
    : undefined;
  const entry = isRecord(entries?.zeroinbox) ? entries.zeroinbox : undefined;
  return isRecord(entry?.config) ? entry.config : {};
}

function resolvePath(rawPath, baseDir) {
  const expanded = expandHome(rawPath);
  return path.isAbsolute(expanded) ? expanded : path.resolve(baseDir, expanded);
}

function resolveConfigPath(ctx) {
  const cfg = readPluginConfig(ctx);
  const configured = readString(cfg.configPath) ?? readString(process.env.ZEROINBOX_CONFIG);
  if (configured) {
    return resolvePath(configured, pluginRoot);
  }
  return pluginConfigPath;
}

function readDotenv(filePath) {
  let content;
  try {
    content = fs.readFileSync(filePath, "utf8");
  } catch {
    return {};
  }
  const loaded = {};
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const equals = trimmed.indexOf("=");
    if (equals <= 0) {
      continue;
    }
    const name = trimmed.slice(0, equals).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || process.env[name] !== undefined) {
      continue;
    }
    let value = trimmed.slice(equals + 1).trim();
    if (
      value.length >= 2
      && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    loaded[name] = value;
  }
  return loaded;
}

function readProcEnv() {
  try {
    const loaded = {};
    for (const entry of fs.readFileSync("/proc/self/environ", "utf8").split("\0")) {
      const equals = entry.indexOf("=");
      if (equals > 0) {
        loaded[entry.slice(0, equals)] = entry.slice(equals + 1);
      }
    }
    return loaded;
  } catch {
    return {};
  }
}

function runtimeEnv() {
  const picked = {};
  for (const source of [readProcEnv(), process.env]) {
    for (const [key, value] of Object.entries(source)) {
      if (/^(ZEROINBOX|LITELLM)_/.test(key)) {
        picked[key] = value;
      }
    }
  }
  return picked;
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return {};
  }
}

function readKeyValues(filePath) {
  let content;
  try {
    content = fs.readFileSync(filePath, "utf8");
  } catch {
    return {};
  }
  const loaded = {};
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const equals = trimmed.indexOf("=");
    if (equals <= 0) {
      continue;
    }
    const name = trimmed.slice(0, equals).trim();
    let value = trimmed.slice(equals + 1).trim();
    if (
      value.length >= 2
      && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    loaded[name] = value;
  }
  return loaded;
}

function readConfigValues(filePath) {
  return filePath.endsWith(".json") ? readJson(filePath) : readKeyValues(filePath);
}

function resolveEnv(ctx) {
  const cfg = readPluginConfig(ctx);
  const configPath = resolveConfigPath(ctx);
  const fileConfig = readConfigValues(configPath);
  const envFile = readString(cfg.envFile)
    ?? readString(fileConfig.envFile)
    ?? readString(fileConfig.ZEROINBOX_ENV_FILE)
    ?? ".env";
  if (!envFile) {
    return {};
  }
  return readDotenv(resolvePath(envFile, path.dirname(configPath)));
}

function runProcess(command, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: { ...process.env, PYTHONUNBUFFERED: "1", ...options.env },
      signal: options.signal,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = options.timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          child.kill("SIGTERM");
        }, options.timeoutMs)
      : undefined;
    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (error) => {
      if (timer) {
        clearTimeout(timer);
      }
      resolve({ code: -1, stdout, stderr: `${stderr}${error.message}`, timedOut });
    });
    child.on("close", (code) => {
      if (timer) {
        clearTimeout(timer);
      }
      resolve({ code: code ?? -1, stdout, stderr, timedOut });
    });
  });
}

async function setupPython(signal) {
  const create = await runProcess(
    readString(process.env.ZEROINBOX_BOOTSTRAP_PYTHON) ?? "python3",
    ["-m", "venv", venvDir],
    { cwd: pluginRoot, signal, timeoutMs: 120_000 },
  );
  if (create.code !== 0) {
    throw new Error(`ZEROINBOX Python venv setup failed: ${create.stderr || create.stdout}`);
  }
  const install = await runProcess(venvPython, ["-m", "pip", "install", "-r", requirementsPath], {
    cwd: pluginRoot,
    signal,
    timeoutMs: 300_000,
  });
  if (install.code !== 0) {
    throw new Error(`ZEROINBOX requirements install failed: ${install.stderr || install.stdout}`);
  }
}

async function resolvePython(ctx, signal) {
  const cfg = readPluginConfig(ctx);
  const configured = readString(cfg.pythonPath) ?? readString(process.env.ZEROINBOX_PYTHON);
  if (configured) {
    return expandHome(configured);
  }
  if (await exists(venvPython)) {
    return venvPython;
  }
  const autoSetup = cfg.autoSetupPython !== false || process.env.ZEROINBOX_AUTO_SETUP === "1";
  if (autoSetup) {
    await setupPython(signal);
    return venvPython;
  }
  return "python3";
}

async function runZeroinbox(ctx, params, signal) {
  const cfg = readPluginConfig(ctx);
  const raw = readString(params.raw) ?? readString(cfg.defaultArgs) ?? "sort --commit";
  const python = await resolvePython(ctx, signal);
  const configPath = resolveConfigPath(ctx);
  const env = resolveEnv(ctx);
  const result = await runProcess(
    python,
    ["-m", "zeroinbox.cli", "--config", configPath, "--json", "--raw", raw],
    {
      cwd: pluginRoot,
      signal,
      timeoutMs: 600_000,
      env: {
        ...env,
        ...runtimeEnv(),
        PYTHONPATH: pluginRoot,
      },
    },
  );
  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    payload = undefined;
  }
  if (result.code !== 0 || payload?.ok === false) {
    const error = payload?.error ?? `${result.stderr}\n${result.stdout}`.trim();
    throw new Error(error || `ZEROINBOX exited with ${result.code}`);
  }
  return payload ?? { ok: true, text: result.stdout.trim() };
}

function createTool(ctx) {
  return {
    name: "zeroinbox_run",
    label: "ZEROINBOX",
    displaySummary: "Run the standalone ZEROINBOX mail sorter.",
    description: "Check IMAP status, list folders, classify samples, or sort mail.",
    parameters: toolParameters,
    async execute(_toolCallId, params, signal) {
      const payload = await runZeroinbox(ctx, isRecord(params) ? params : {}, signal);
      return {
        content: [{ type: "text", text: payload.text ?? "ZEROINBOX done." }],
        details: payload,
      };
    },
  };
}

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(`${JSON.stringify(payload, null, 2)}\n`);
}

async function deliverIfConfigured(api, payload) {
  const delivery = isRecord(readPluginConfig(api).delivery) ? readPluginConfig(api).delivery : {};
  const target = readString(delivery.target);
  if (!target) {
    return false;
  }
  const channel = readString(delivery.channel) ?? "telegram";
  const adapter = await api.runtime.channel.outbound.loadAdapter(channel);
  const account = readString(delivery.accountId) ? { accountId: delivery.accountId } : {};
  const reportPath = readString(payload.reportPath);
  if (reportPath && adapter?.sendMedia) {
    await adapter.sendMedia({
      cfg: api.runtime.config?.current?.() ?? api.config,
      to: target,
      text: payload.text ?? "ZEROINBOX",
      mediaUrl: reportPath,
      mediaLocalRoots: [path.dirname(reportPath)],
      forceDocument: true,
      ...account,
    });
    return true;
  }
  if (adapter?.sendText) {
    await adapter.sendText({
      cfg: api.runtime.config?.current?.() ?? api.config,
      to: target,
      text: payload.text ?? "ZEROINBOX done.",
      ...account,
    });
    return true;
  }
  throw new Error(`No outbound adapter configured for ${channel}.`);
}

async function runZeroinboxCommand(api, raw) {
  const payload = await runZeroinbox(api, { raw });
  const reportPath = readString(payload.reportPath);
  if (reportPath) {
    return { mediaUrl: reportPath };
  }
  return { text: payload.text ?? "ZEROINBOX done." };
}

function registerWebhook(api) {
  const cfg = readPluginConfig(api);
  const webhook = isRecord(cfg.webhook) ? cfg.webhook : {};
  if (webhook.enabled === false) {
    return;
  }
  const routePath = readString(webhook.path) ?? defaultWebhookPath;
  api.registerHttpRoute({
    path: routePath,
    auth: "gateway",
    match: "exact",
    replaceExisting: true,
    async handler(req, res) {
      if (req.method !== "POST") {
        res.setHeader("Allow", "POST");
        sendJson(res, 405, { ok: false, error: "method_not_allowed" });
        return true;
      }
      try {
        const raw = readString(webhook.args) ?? "sort --commit";
        const payload = await runZeroinbox(api, { raw });
        const delivered = await deliverIfConfigured(api, payload);
        sendJson(res, 200, {
          ...payload,
          ...(readString(payload.reportPath) ? { media: `MEDIA:${payload.reportPath}` } : {}),
          delivered,
        });
      } catch (error) {
        api.logger.error?.(`zeroinbox webhook failed: ${error instanceof Error ? error.message : String(error)}`);
        sendJson(res, 500, { ok: false, error: error instanceof Error ? error.message : String(error) });
      }
      return true;
    },
  });
  api.logger.info?.(`zeroinbox webhook registered at ${routePath}`);
}

export default definePluginEntry({
  id: "zeroinbox",
  name: "ZEROINBOX",
  description: "Standalone IMAP and LiteLLM mail sorter with a /zeroinbox command.",
  configSchema,
  register(api) {
    api.registerTool((ctx) => createTool(ctx), { names: ["zeroinbox_run"] });
    api.registerCommand({
      name: "zeroinbox",
      description: "Run ZEROINBOX mail sorting or status commands.",
      acceptsArgs: true,
      requireAuth: true,
      handler: async (ctx) => {
        const raw = readString(ctx?.args) ?? "";
        return runZeroinboxCommand(api, raw);
      },
    });
    registerWebhook(api);
  },
});
