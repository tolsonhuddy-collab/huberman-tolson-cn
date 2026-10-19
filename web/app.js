/* Reader controls adapted from the approved template; directory filters are local. */
(() => {
  const root = document.documentElement;
  const read = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } };
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
  const themeToggle = document.getElementById('theme-toggle');
  const applyTheme = (theme) => {
    root.dataset.theme = theme === 'dark' ? 'dark' : 'light';
    themeToggle?.setAttribute('aria-label', root.dataset.theme === 'dark' ? '切换为浅色阅读' : '切换为深色阅读');
    save('huberman-reading-theme', root.dataset.theme);
  };
  applyTheme(read('huberman-reading-theme', 'light'));
  themeToggle?.addEventListener('click', () => applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));

  const chapters = [...document.querySelectorAll('.chapter, #terms')];
  function updateProgress() {
    const max = Math.max(1, root.scrollHeight - window.innerHeight);
    const progress = Math.min(100, Math.max(0, Math.round(window.scrollY / max * 100)));
    const bar = document.getElementById('progress-bar');
    const label = document.getElementById('progress-label');
    if (bar) bar.style.width = `${progress}%`;
    if (label) label.textContent = `阅读进度 ${progress}%`;
    let current = chapters[0]?.id;
    for (const chapter of chapters) if (chapter.getBoundingClientRect().top < window.innerHeight * .38) current = chapter.id;
    document.querySelectorAll('.toc-links a').forEach(a => {
      const active = a.hash === `#${current}`;
      a.classList.toggle('active', active);
      if (active) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
    });
  }
  let size = Math.min(24, Math.max(16, Number(read('huberman-reading-size', '18')) || 18));
  const down = document.getElementById('font-down'), up = document.getElementById('font-up'), fontLabel = document.getElementById('font-label');
  function applySize() {
    root.style.setProperty('--read-size', `${size}px`);
    if (fontLabel) fontLabel.value = String(size);
    if (down) down.disabled = size <= 16;
    if (up) up.disabled = size >= 24;
    save('huberman-reading-size', String(size));
    updateProgress();
  }
  down?.addEventListener('click', () => { size = Math.max(16, size - 2); applySize(); });
  up?.addEventListener('click', () => { size = Math.min(24, size + 2); applySize(); });
  applySize();
  document.querySelectorAll('.mobile-toc a').forEach(a => a.addEventListener('click', () => a.closest('details')?.removeAttribute('open')));
  let frame = false;
  window.addEventListener('scroll', () => { if (!frame) { frame = true; requestAnimationFrame(() => { updateProgress(); frame = false; }); } }, { passive: true });
  window.addEventListener('resize', updateProgress);
  document.querySelectorAll('.term').forEach(d => d.addEventListener('toggle', updateProgress));
  window.addEventListener('load', updateProgress);

  const search = document.getElementById('episode-search');
  const kind = document.getElementById('kind-filter');
  const status = document.getElementById('status-filter');
  const cards = [...document.querySelectorAll('.episode-card')];
  const catalogTabs = [...document.querySelectorAll('[data-catalog-status]')];
  function filterCatalog() {
    const query = (search?.value || '').trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const matches = (!query || card.dataset.search.includes(query)) &&
        (!kind || kind.value === 'all' || card.dataset.kind === kind.value) &&
        (!status || status.value === 'all' || card.dataset.availability === status.value);
      card.hidden = !matches;
      if (matches) visible++;
    }
    const count = document.getElementById('result-count'), empty = document.getElementById('no-results');
    if (count) count.textContent = `显示 ${visible} / ${cards.length} 期`;
    if (empty) empty.hidden = visible !== 0;
    const feature = document.getElementById('front-story');
    if (feature) feature.hidden = !!query || (!!kind && kind.value !== 'all') || (!!status && status.value !== 'all');
    catalogTabs.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.catalogStatus === (status?.value || 'all'))));
  }
  catalogTabs.forEach(button => button.addEventListener('click', () => {
    if (status) status.value = button.dataset.catalogStatus;
    filterCatalog();
  }));
  [search, kind, status].forEach(control => control?.addEventListener('input', filterCatalog));
  if (search) filterCatalog();
})();
