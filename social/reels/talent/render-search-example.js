// Renders the real employer search UI from candidates/index.html with EXAMPLE profiles (no real people).
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
  await p.goto('http://localhost:8765/candidates/#hiring', { waitUntil: 'networkidle' }).catch(() => {});
  await p.waitForTimeout(1200);
  await p.evaluate(() => {
    const iso = d => d;
    PROFILES = [
      { pid: 'a', headline: 'Ex-RE High Threat IEDD operator, 12 years', categories: ['EOD', 'IEDD'], years: 12, regions: ['Middle East', 'Africa'], rotation: '8/4 or 6/3', rate: '£450/day', based: 'UK', languages: 'English, basic Arabic', clearance: 'SC (lapsed 2024)', quals: 'IMAS EOD Level 3+, HEAT, FREC 4', summary: 'Iraq, Afghanistan, Mali (UN). Team leader.', available_from: '2026-11-01', has_cv: true },
      { pid: 'b', headline: 'HE paramedic, remote and offshore medicine', categories: ['Medical'], years: 9, regions: ['Africa', 'Middle East'], rotation: '4/4', rate: '£300/day', based: 'UK', languages: 'English, French', clearance: '', quals: 'HCPC paramedic, FREC 5, PHTLS', summary: 'Somalia, South Sudan, Iraq. NGO and security clients.', available_from: '2026-11-15', has_cv: true },
      { pid: 'c', headline: 'Mine action team leader, NTS and EORE', categories: ['Survey & Clearance', 'EOD'], years: 7, regions: ['Europe', 'Middle East'], rotation: 'Any', rate: '', based: 'Croatia', languages: 'English, Croatian, Ukrainian', clearance: '', quals: 'IMAS EOD Level 3, NTS, EORE', summary: 'Ukraine, Syria. Mechanical and manual teams.', available_from: '2026-11-01', has_cv: false },
      { pid: 'd', headline: 'Close protection team leader, hostile environments', categories: ['Security'], years: 15, regions: ['Middle East', 'Africa'], rotation: '8/4', rate: '£400/day', based: 'UK', languages: 'English', clearance: 'SC', quals: 'SIA CP, FREC 4, HEAT', summary: 'Iraq, Libya, Yemen. Diplomatic and NGO clients.', available_from: '2026-12-01', has_cv: true }
    ];
    document.getElementById('h-search').hidden = false;
    for (const id of ['h-signup', 'h-acct', 'h-sent', 'h-intro']) { const e = document.getElementById(id); if (e) e.hidden = true; }
    drawResults();
    for (const h of document.querySelectorAll('h2')) { if (/sign up to search/i.test(h.textContent)) { const pn = h.closest('.panel,section,form,div'); if (pn) pn.style.display = 'none'; } }
    for (const e of document.querySelectorAll('*')) { const cs = getComputedStyle(e); if (cs.position === 'sticky' || cs.position === 'fixed') e.style.position = 'static'; }
  });
  await p.waitForTimeout(500);
  await p.screenshot({ path: process.argv[2] + '/search-d.png', fullPage: true });
  const y = await p.evaluate(() => document.getElementById('h-search').getBoundingClientRect().top + scrollY);
  console.log('searchTop', y);
  await b.close();
})();
