// === Shared Navigation & Footer Components ===
(function() {
  const currentPage = document.documentElement.getAttribute('data-page') || '';
  // Determine base path for links (handles /blog/ subdirectory)
  const base = location.pathname.includes('/blog/') ? '../' : '';

  function navLink(href, label, page) {
    const cls = currentPage === page ? ' class="active"' : '';
    return `<a href="${base}${href}"${cls}>${label}</a>`;
  }

  // --- Navigation ---
  const headerHTML = `
  <header class="site-header">
    <div class="header-inner">
      <a href="${base}index.html" class="logo">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M23.643 4.937c-.835.37-1.732.62-2.675.733a4.67 4.67 0 002.048-2.578 9.3 9.3 0 01-2.958 1.13 4.66 4.66 0 00-7.938 4.25 13.229 13.229 0 01-9.602-4.868c-.4.69-.63 1.49-.63 2.342A4.66 4.66 0 003.96 9.824a4.647 4.647 0 01-2.11-.583v.06a4.66 4.66 0 003.737 4.568 4.692 4.692 0 01-2.104.08 4.661 4.661 0 004.352 3.234 9.348 9.348 0 01-5.786 1.995 9.5 9.5 0 01-1.112-.065 13.175 13.175 0 007.14 2.093c8.57 0 13.255-7.098 13.255-13.254 0-.2-.005-.402-.014-.602a9.47 9.47 0 002.323-2.41l.002-.003z"/></svg>
        Twitter Video Downloader
      </a>
      <button class="hamburger" aria-label="メニュー" onclick="this.nextElementSibling.classList.toggle('open')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <nav class="nav-links">
        ${navLink('index.html', 'ホーム', 'home')}
        ${navLink('guide.html', '使い方', 'guide')}
        ${navLink('blog.html', 'ブログ', 'blog')}
        ${navLink('faq.html', 'よくある質問', 'faq')}
        ${navLink('about.html', 'このサイトについて', 'about')}
      </nav>
    </div>
  </header>`;

  // --- Footer ---
  const footerHTML = `
  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-columns">
        <div class="footer-column">
          <h4>ツール</h4>
          <ul>
            <li><a href="${base}index.html">ホーム</a></li>
            <li><a href="${base}guide.html">使い方ガイド</a></li>
            <li><a href="${base}faq.html">よくある質問</a></li>
          </ul>
        </div>
        <div class="footer-column">
          <h4>情報</h4>
          <ul>
            <li><a href="${base}blog.html">ブログ</a></li>
            <li><a href="${base}about.html">このサイトについて</a></li>
            <li><a href="${base}contact.html">お問い合わせ</a></li>
          </ul>
        </div>
        <div class="footer-column">
          <h4>法的情報</h4>
          <ul>
            <li><a href="${base}privacy.html">プライバシーポリシー</a></li>
            <li><a href="${base}terms.html">利用規約</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        &copy; ${new Date().getFullYear()} HaraTeck合同会社 All rights reserved.
      </div>
    </div>
  </footer>`;

  // --- Inject ---
  const headerEl = document.getElementById('site-header');
  const footerEl = document.getElementById('site-footer');
  if (headerEl) headerEl.innerHTML = headerHTML;
  if (footerEl) footerEl.innerHTML = footerHTML;
})();
