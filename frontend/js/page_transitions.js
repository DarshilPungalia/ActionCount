/**
 * page_transitions.js — shared page transition helper.
 *
 * On DOMContentLoaded: adds "page-enter" class to body for the enter animation.
 * On same-origin <a> clicks: briefly applies "page-exit" class, then navigates.
 *
 * Skips:
 *   - External links
 *   - Links that open in a new tab
 *   - Anchor-only links (#hash)
 *   - Links with data-no-transition
 */
(function () {
  'use strict';

  // Apply enter animation on every page load
  document.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('page-enter');
  });

  // Intercept clicks for exit animation
  document.addEventListener('click', function (e) {
    // Walk up the DOM to find the nearest <a>
    let target = e.target;
    while (target && target.tagName !== 'A') target = target.parentElement;
    if (!target) return;

    const href = target.getAttribute('href');
    if (!href) return;

    // Skip: new tab, external, hash-only, download, data-no-transition
    if (
      target.target === '_blank' ||
      target.hasAttribute('download') ||
      target.hasAttribute('data-no-transition') ||
      href.startsWith('#') ||
      href.startsWith('javascript:') ||
      (href.startsWith('http') && !href.startsWith(window.location.origin))
    ) return;

    // Same-origin navigation — play exit, then navigate
    e.preventDefault();
    document.body.classList.add('page-exit');
    setTimeout(function () {
      window.location.href = href;
    }, 220); // matches pageExit animation duration
  });
})();
