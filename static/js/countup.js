/**
 * EduBridge Global Count-Up Animation System
 *
 * Provides a high-performance, accessible, and reusable count-up counter
 * powered by requestAnimationFrame, cubic ease-out, and staggered scheduling.
 *
 * Respects prefers-reduced-motion and supports integers, floats,
 * time values, percentages, and custom suffixes/prefixes.
 */

(function (window, document) {
  'use strict';

  // Cubic Ease-Out
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  // Format Helper
  function formatValue(currentValue, decimals, format, prefix, suffix) {
    let formatted = '';

    if (format === 'time_hours_mins') {
      // currentValue in minutes
      const totalMins = Math.round(currentValue);
      const hours = Math.floor(totalMins / 60);
      const mins = totalMins % 60;
      if (hours > 0) {
        formatted = `${hours}h ${mins}m`;
      } else {
        formatted = `${mins}m`;
      }
    } else if (format === 'time_hours') {
      // Decimal hours, e.g. 12.5 hrs
      formatted = `${currentValue.toFixed(decimals)}h`;
    } else {
      if (decimals > 0) {
        formatted = currentValue.toFixed(decimals);
      } else {
        formatted = Math.round(currentValue).toLocaleString();
      }
    }

    return `${prefix || ''}${formatted}${suffix || ''}`;
  }

  const CountUp = {
    /**
     * Animate a single DOM element from start to end.
     */
    animate: function (el, options) {
      if (!el) return;

      // Cancel any ongoing animation on this element
      if (el._countUpRaf) {
        cancelAnimationFrame(el._countUpRaf);
        el._countUpRaf = null;
      }

      // Check user reduced motion preference
      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      // Read configuration from options or data attributes
      const rawTarget = options && options.end !== undefined
        ? options.end
        : (el.getAttribute('data-countup-target') || el.getAttribute('data-target') || el.textContent);

      // Handle "N/A" or non-numeric gracefully
      const strVal = String(rawTarget).trim();
      if (strVal === 'N/A' || strVal === '—' || isNaN(parseFloat(strVal))) {
        el.textContent = strVal;
        return;
      }

      const endValue = parseFloat(strVal);
      const startValue = (options && options.start !== undefined)
        ? options.start
        : parseFloat(el.getAttribute('data-countup-start') || '0');

      const duration = (options && options.duration !== undefined)
        ? options.duration
        : parseInt(el.getAttribute('data-countup-duration') || '1200', 10);

      const decimals = (options && options.decimals !== undefined)
        ? options.decimals
        : (el.hasAttribute('data-countup-decimals') ? parseInt(el.getAttribute('data-countup-decimals'), 10) : (strVal.includes('.') ? 1 : 0));

      const prefix = (options && options.prefix !== undefined)
        ? options.prefix
        : (el.getAttribute('data-countup-prefix') || '');

      const suffix = (options && options.suffix !== undefined)
        ? options.suffix
        : (el.getAttribute('data-countup-suffix') || '');

      const format = (options && options.format !== undefined)
        ? options.format
        : (el.getAttribute('data-countup-format') || 'number');

      // If reduced motion is requested, snap directly to end value
      if (prefersReducedMotion) {
        el.textContent = formatValue(endValue, decimals, format, prefix, suffix);
        return;
      }

      // Initial visual state
      el.textContent = formatValue(startValue, decimals, format, prefix, suffix);

      const startTime = performance.now();

      function step(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easeOutCubic(progress);

        const currentVal = startValue + (endValue - startValue) * easedProgress;
        el.textContent = formatValue(currentVal, decimals, format, prefix, suffix);

        if (progress < 1) {
          el._countUpRaf = requestAnimationFrame(step);
        } else {
          el._countUpRaf = null;
          // Ensure exact final value is set
          el.textContent = formatValue(endValue, decimals, format, prefix, suffix);
        }
      }

      el._countUpRaf = requestAnimationFrame(step);
    },

    /**
     * Animate all [data-countup] elements within a container, with optional staggered delay.
     */
    animateAll: function (container, staggerMs) {
      const root = container || document;
      const elements = root.querySelectorAll('[data-countup]');
      const delay = staggerMs !== undefined ? staggerMs : 45;

      elements.forEach(function (el, index) {
        if (delay > 0) {
          setTimeout(function () {
            CountUp.animate(el);
          }, index * delay);
        } else {
          CountUp.animate(el);
        }
      });
    },

    /**
     * Programmatically update an element's target and re-trigger animation.
     */
    update: function (el, newTarget, options) {
      if (!el) return;
      el.setAttribute('data-countup-target', newTarget);
      const opts = Object.assign({}, options || {}, { end: newTarget, start: 0 });
      CountUp.animate(el, opts);
    },

    /**
     * Cancel ongoing animation and reset value to 0.
     */
    reset: function (el) {
      if (!el) return;
      if (el._countUpRaf) {
        cancelAnimationFrame(el._countUpRaf);
        el._countUpRaf = null;
      }
      el.textContent = '0';
    }
  };

  /**
   * EduBridge Sequential Text Reveal System for Academic Statuses
   * Revealing letters: P -> PA -> PAS -> PASS -> ... -> PASSING
   */
  const TextReveal = {
    reveal: function (el, options) {
      if (!el) return;
      if (el._textRevealTimer) {
        clearInterval(el._textRevealTimer);
        el._textRevealTimer = null;
      }
      const fullText = (options && options.text !== undefined)
        ? String(options.text).trim()
        : (el.getAttribute('data-text-reveal') || el.textContent).trim();

      if (!fullText) return;

      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (prefersReducedMotion) {
        el.textContent = fullText;
        return;
      }

      // Accessibility: preserve full text for screen readers without intermediate character spam
      el.setAttribute('aria-label', fullText);
      el.setAttribute('role', 'status');

      const speed = (options && options.speed) || 35; // ms per char
      let idx = 0;
      el.textContent = '';

      el._textRevealTimer = setInterval(function () {
        idx++;
        el.textContent = fullText.slice(0, idx);
        if (idx >= fullText.length) {
          clearInterval(el._textRevealTimer);
          el._textRevealTimer = null;
          el.textContent = fullText;
        }
      }, speed);
    },

    revealAll: function (container, staggerMs) {
      const root = container || document;
      const elements = root.querySelectorAll('[data-text-reveal], .status-reveal');
      const delay = staggerMs !== undefined ? staggerMs : 60;

      elements.forEach(function (el, index) {
        if (delay > 0) {
          setTimeout(function () {
            TextReveal.reveal(el);
          }, index * delay);
        } else {
          TextReveal.reveal(el);
        }
      });
    },

    update: function (el, newText, options) {
      if (!el) return;
      el.setAttribute('data-text-reveal', newText);
      const opts = Object.assign({}, options || {}, { text: newText });
      TextReveal.reveal(el, opts);
    }
  };

  // Expose globally
  window.EduBridgeCountUp = CountUp;
  window.CountUp = CountUp;
  window.EduBridgeTextReveal = TextReveal;
  window.TextReveal = TextReveal;

  // Auto-init on page load and page restores
  document.addEventListener('DOMContentLoaded', function () {
    CountUp.animateAll(document, 40);
    TextReveal.revealAll(document, 60);
  });

  window.addEventListener('pageshow', function () {
    CountUp.animateAll(document, 30);
    TextReveal.revealAll(document, 50);
  });

})(window, document);

