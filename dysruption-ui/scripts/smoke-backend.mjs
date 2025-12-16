const UI_BASE_URL = (process.env.UI_BASE_URL || '').trim().replace(/\/+$/, '');

if (!UI_BASE_URL) {
  console.error('Missing UI_BASE_URL (e.g. https://your-ui.up.railway.app)');
  process.exit(2);
}

const DIAG_URL = `${UI_BASE_URL}/api/backend/diagnostics`;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchJson(url) {
  const resp = await fetch(url, { method: 'GET', cache: 'no-store' });
  const text = await resp.text().catch(() => '');
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    // keep null
  }
  return { resp, text, json };
}

async function main() {
  const attempts = Number(process.env.SMOKE_ATTEMPTS || 8);
  const delayMs = Number(process.env.SMOKE_DELAY_MS || 7500);

  let last = null;
  for (let i = 1; i <= attempts; i++) {
    try {
      last = await fetchJson(DIAG_URL);
      const { resp, json, text } = last;

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status} ${resp.statusText} ${text?.slice(0, 200) || ''}`);
      }

      const ok = !!json?.ok;
      const rootOk = json?.probes?.root?.ok === true;
      const docsOk = json?.probes?.docs?.ok === true;

      if (!ok || !rootOk) {
        throw new Error(`Diagnostics not healthy: ok=${ok} rootOk=${rootOk} docsOk=${docsOk}`);
      }

      console.log('SMOKE PASS');
      console.log(JSON.stringify({
        diag: {
          url: DIAG_URL,
          build: json?.build || null,
          env: {
            CVA_BACKEND_URL_resolved: json?.env?.CVA_BACKEND_URL_resolved || null,
            CVA_API_TOKEN_present: json?.env?.CVA_API_TOKEN_present ?? null,
          },
          probes: json?.probes || null,
        },
      }, null, 2));
      return;
    } catch (e) {
      const msg = e?.message || String(e);
      console.error(`Attempt ${i}/${attempts} failed: ${msg}`);
      if (i < attempts) await sleep(delayMs);
    }
  }

  console.error('SMOKE FAIL');
  if (last?.json) {
    console.error(JSON.stringify(last.json, null, 2));
  } else if (last?.text) {
    console.error(last.text.slice(0, 2000));
  }
  process.exit(1);
}

main().catch((e) => {
  console.error(e?.message || String(e));
  process.exit(1);
});
