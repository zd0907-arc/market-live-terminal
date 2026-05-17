#!/usr/bin/env node
import fs from 'node:fs/promises';
import http from 'node:http';
import { spawn } from 'node:child_process';

const args = Object.fromEntries(
  process.argv.slice(2).map((arg) => {
    const [key, ...rest] = arg.split('=');
    return [key.replace(/^--/, ''), rest.join('=') || '1'];
  }),
);

const url = args.url;
const screenshotPath = args.screenshot || '/tmp/market-live-terminal-page-probe.png';
const port = Number(args.port || 9222);
const timeoutMs = Number(args.timeoutMs || 45000);
const settleMs = Number(args.settleMs || 8000);
const chromePath = args.chrome || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

if (!url) {
  console.error('missing --url');
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const requestJson = (requestUrl) => new Promise((resolve, reject) => {
  const req = http.get(requestUrl, (res) => {
    let data = '';
    res.setEncoding('utf8');
    res.on('data', (chunk) => { data += chunk; });
    res.on('end', () => {
      try {
        resolve(JSON.parse(data));
      } catch (error) {
        reject(error);
      }
    });
  });
  req.on('error', reject);
  req.setTimeout(2000, () => {
    req.destroy(new Error(`timeout ${requestUrl}`));
  });
});

let nextId = 1;

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.pending = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    this.ws.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      if (payload.id && this.pending.has(payload.id)) {
        const { resolve, reject } = this.pending.get(payload.id);
        this.pending.delete(payload.id);
        if (payload.error) reject(new Error(JSON.stringify(payload.error)));
        else resolve(payload.result);
      }
    });
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });
  }

  send(method, params = {}) {
    const id = nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      // ignore
    }
  }
}

const userDataDir = `/tmp/market-live-terminal-cdp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const chrome = spawn(
  chromePath,
  [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--no-proxy-server',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    '--window-size=1440,1000',
    'about:blank',
  ],
  { stdio: ['ignore', 'pipe', 'pipe'] },
);

let stderr = '';
chrome.stderr.on('data', (chunk) => {
  stderr += chunk.toString();
});

const deadline = Date.now() + timeoutMs;
let client;

try {
  let tabs;
  while (Date.now() < deadline) {
    try {
      tabs = await requestJson(`http://127.0.0.1:${port}/json`);
      if (Array.isArray(tabs) && tabs.length) break;
    } catch {
      // wait
    }
    await sleep(250);
  }
  if (!Array.isArray(tabs) || !tabs.length) {
    throw new Error('Chrome debugging endpoint did not become ready');
  }
  const tab = tabs.find((item) => item.type === 'page') || tabs[0];
  client = new CdpClient(tab.webSocketDebuggerUrl);
  await client.connect();
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Page.navigate', { url });
  const settleDeadline = Date.now() + settleMs;
  let bodyLength = 0;
  let bodyPreview = '';
  while (Date.now() < settleDeadline) {
    const bodyPoll = await client.send('Runtime.evaluate', {
      expression: 'document.body ? document.body.innerText.slice(0, 2000) : ""',
      returnByValue: true,
    });
    bodyPreview = bodyPoll.result?.value || '';
    bodyLength = bodyPreview.length;
    if (bodyLength > 100 && !bodyPreview.includes('加载中...')) {
      break;
    }
    await sleep(1000);
  }

  const titleResult = await client.send('Runtime.evaluate', {
    expression: 'document.title',
    returnByValue: true,
  });
  const bodyResult = await client.send('Runtime.evaluate', {
    expression: 'document.body ? document.body.innerText.slice(0, 2000) : ""',
    returnByValue: true,
  });
  const bodyLengthResult = await client.send('Runtime.evaluate', {
    expression: 'document.body ? document.body.innerText.length : 0',
    returnByValue: true,
  });
  const errorTextResult = await client.send('Runtime.evaluate', {
    expression: 'Array.from(document.querySelectorAll("*")).map(n => n.innerText || "").filter(t => /渲染失败|加载失败|Error|error/i.test(t)).slice(0, 10).join("\\n---\\n")',
    returnByValue: true,
  });
  const screenshot = await client.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  });
  await fs.writeFile(screenshotPath, Buffer.from(screenshot.data, 'base64'));
  const stat = await fs.stat(screenshotPath);
  const output = {
    ok: stat.size > 10000 && Number(bodyLengthResult.result?.value || 0) > 100,
    url,
    title: titleResult.result?.value || '',
    body_length: Number(bodyLengthResult.result?.value || 0),
    body_preview: bodyResult.result?.value || '',
    error_text: errorTextResult.result?.value || '',
    screenshot: screenshotPath,
    screenshot_bytes: stat.size,
    stderr_tail: stderr.slice(-1000),
  };
  console.log(JSON.stringify(output, null, 2));
  process.exit(output.ok ? 0 : 1);
} catch (error) {
  console.log(JSON.stringify({
    ok: false,
    url,
    error: error instanceof Error ? error.message : String(error),
    stderr_tail: stderr.slice(-1000),
  }, null, 2));
  process.exit(1);
} finally {
  client?.close();
  chrome.kill('SIGTERM');
}
