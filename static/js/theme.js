/**
 * theme.js — Dark / Light mode manager for Trayector-IA
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'trayector-theme';
  const DARK_CLASS  = 'dark-mode';

  // ── Apply stored / preferred theme immediately (no flicker) ──
  const stored = localStorage.getItem(STORAGE_KEY);
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  if (stored === 'dark' || (!stored && prefersDark)) {
    document.documentElement.classList.add(DARK_CLASS);
  }

  // ── After DOM is ready, wire up toggle ────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;

    // Sync toggle visual state
    const syncToggle = () => {
      const isDark = document.documentElement.classList.contains(DARK_CLASS);
      toggle.setAttribute('aria-checked', isDark);
      toggle.setAttribute('aria-label', isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');

      // Update icons if present
      const sunIcon = document.getElementById('icon-sun');
      const moonIcon = document.getElementById('icon-moon');
      if (sunIcon)  sunIcon.style.opacity  = isDark ? '0.4' : '1';
      if (moonIcon) moonIcon.style.opacity = isDark ? '1' : '0.4';
    };

    toggle.addEventListener('click', () => {
      const isDark = document.documentElement.classList.toggle(DARK_CLASS);
      localStorage.setItem(STORAGE_KEY, isDark ? 'dark' : 'light');
      syncToggle();
    });

    syncToggle();

    // ── Highlight active nav link ─────────────────────────────
    const links = document.querySelectorAll('nav.main-nav a');
    const path  = window.location.pathname;

    links.forEach(link => {
      const href = link.getAttribute('href');
      const isActive =
        (href === '/' && path === '/') ||
        (href !== '/' && path.startsWith(href));
      link.classList.toggle('active', isActive);
    });

    // ── Mobile hamburger ──────────────────────────────────────
    const hamburger = document.querySelector('.hamburger');
    const nav       = document.querySelector('nav.main-nav');

    if (hamburger && nav) {
      hamburger.addEventListener('click', () => {
        nav.classList.toggle('open');
        const isOpen = nav.classList.contains('open');
        hamburger.setAttribute('aria-expanded', isOpen);
      });

      // Close on nav link click (mobile)
      nav.querySelectorAll('a').forEach(a => {
        a.addEventListener('click', () => nav.classList.remove('open'));
      });
    }
  });
})();
