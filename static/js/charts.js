/**
 * EduBridge Dynamic SVG Chart Rendering & Animation Engine
 *
 * Provides a lightweight, high-performance, accessible, dependency-free SVG chart library:
 * - Line & Area Charts with animated stroke drawing & area fade
 * - Vertical & Horizontal Bar Charts with smooth height/width growth from zero
 * - Donut & Pie Charts with animated circle dashoffset strokes & center metrics
 * - Floating high-contrast interactive tooltips
 * - Dynamic empty state and loading skeleton states
 * - Reset and replay mechanisms on filter/ID/tab changes
 */

(function (window, document) {
  'use strict';

  // Global tooltip singleton
  let tooltipEl = null;

  function getTooltip() {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'edubridge-chart-tooltip';
      tooltipEl.style.position = 'fixed';
      tooltipEl.style.display = 'none';
      tooltipEl.style.pointerEvents = 'none';
      tooltipEl.style.zIndex = '99999';
      tooltipEl.style.padding = '6px 12px';
      tooltipEl.style.borderRadius = '8px';
      tooltipEl.style.background = '#0F172A';
      tooltipEl.style.color = '#FFFFFF';
      tooltipEl.style.fontSize = '0.785rem';
      tooltipEl.style.fontWeight = '600';
      tooltipEl.style.boxShadow = '0 10px 25px -5px rgba(0,0,0,0.3)';
      tooltipEl.style.transition = 'opacity 0.15s ease, transform 0.15s ease';
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  function showTooltip(e, html) {
    const tip = getTooltip();
    tip.innerHTML = html;
    tip.style.display = 'block';
    tip.style.opacity = '1';

    const x = e.clientX + 12;
    const y = e.clientY - 35;
    tip.style.transform = `translate(${x}px, ${y}px)`;
  }

  function hideTooltip() {
    const tip = getTooltip();
    tip.style.display = 'none';
    tip.style.opacity = '0';
  }

  // Pre-configured harmonious color palettes
  const PALETTES = {
    blue: ['#3B82F6', '#60A5FA', '#93C5FD', '#BFDBFE'],
    indigo: ['#6366F1', '#818CF8', '#A5B4FC', '#C7D2FE'],
    emerald: ['#10B981', '#34D399', '#6EE7B7', '#A7F3D0'],
    amber: ['#F59E0B', '#FBBF24', '#FCD34D', '#FDE68A'],
    multi: ['#3B82F6', '#6366F1', '#10B981', '#F59E0B', '#EC4899', '#8B5CF6', '#06B6D4', '#14B8A6']
  };

  const EduBridgeCharts = {
    /**
     * Display a clean loading skeleton in the chart container.
     */
    setLoading: function (container) {
      if (!container) return;
      container.innerHTML = `
        <div class="chart-loading-state" style="height: 100%; min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.75rem; color: var(--text-muted);">
          <div class="chart-spinner" style="width: 28px; height: 28px; border: 3px solid rgba(59,130,246,0.15); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          <span style="font-size: 0.825rem; font-weight: 500;">Retrieving analytics telemetry...</span>
        </div>
      `;
    },

    /**
     * Display a clean, informative empty state.
     */
    renderEmptyState: function (container, message) {
      if (!container) return;
      container.innerHTML = `
        <div class="chart-empty-state" style="height: 100%; min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.5rem; text-align: center; padding: 1.5rem; color: var(--text-muted);">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" style="opacity: 0.5;">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="8" y1="12" x2="16" y2="12"></line>
          </svg>
          <div style="font-size: 0.875rem; font-weight: 600; color: var(--text-secondary);">${message || 'No analytical data recorded for this selection'}</div>
          <small style="font-size: 0.75rem; color: var(--text-muted);">Try selecting a wider date range or alternate cohort filter.</small>
        </div>
      `;
    },

    /**
     * Render an animated Vertical Bar Chart.
     * data: { labels: ['DS', 'OS', 'DB'], values: [85, 92, 78], maxVal: 100, unit: 'Marks' }
     */
    renderBarChart: function (container, data, options) {
      if (!container) return;
      container.innerHTML = '';

      if (!data || !data.values || data.values.length === 0 || data.values.every(v => v === 0)) {
        this.renderEmptyState(container, options && options.emptyMessage);
        return;
      }

      const opts = Object.assign({
        color: '#3B82F6',
        unit: '',
        height: 180,
        showValues: true,
        maxVal: null
      }, options || {});

      const maxVal = opts.maxVal || Math.max(...data.values, 10);
      const labels = data.labels || [];
      const values = data.values || [];

      const chartWrap = document.createElement('div');
      chartWrap.className = 'edubridge-bar-chart';
      chartWrap.style.display = 'flex';
      chartWrap.style.alignItems = 'flex-end';
      chartWrap.style.justifyContent = 'space-around';
      chartWrap.style.height = `${opts.height}px`;
      chartWrap.style.padding = '20px 10px 10px';
      chartWrap.style.position = 'relative';
      chartWrap.style.borderBottom = '1px solid var(--border-subtle)';

      values.forEach((val, idx) => {
        const colGroup = document.createElement('div');
        colGroup.style.display = 'flex';
        colGroup.style.flexDirection = 'column';
        colGroup.style.alignItems = 'center';
        colGroup.style.flex = '1';
        colGroup.style.height = '100%';
        colGroup.style.justifyContent = 'flex-end';
        colGroup.style.position = 'relative';
        colGroup.style.cursor = 'pointer';

        const barTrack = document.createElement('div');
        barTrack.style.width = '24px';
        barTrack.style.maxWidth = '36px';
        barTrack.style.height = '100%';
        barTrack.style.display = 'flex';
        barTrack.style.alignItems = 'flex-end';
        barTrack.style.borderRadius = '6px';
        barTrack.style.background = 'rgba(241, 245, 249, 0.7)';

        const barFill = document.createElement('div');
        barFill.style.width = '100%';
        barFill.style.height = '0%'; // Start at zero height
        barFill.style.background = `linear-gradient(180deg, ${opts.color}, rgba(59, 130, 246, 0.8))`;
        barFill.style.borderRadius = '6px';
        barFill.style.transition = 'height 0.8s cubic-bezier(0.16, 1, 0.3, 1)';

        barTrack.appendChild(barFill);

        const valTag = document.createElement('div');
        valTag.style.fontSize = '0.72rem';
        valTag.style.fontWeight = '700';
        valTag.style.color = 'var(--text-main)';
        valTag.style.marginBottom = '4px';
        valTag.style.opacity = '0';
        valTag.style.transition = 'opacity 0.6s ease';
        valTag.textContent = val;

        const labelTag = document.createElement('div');
        labelTag.style.fontSize = '0.72rem';
        labelTag.style.color = 'var(--text-muted)';
        labelTag.style.marginTop = '6px';
        labelTag.style.whiteSpace = 'nowrap';
        labelTag.style.overflow = 'hidden';
        labelTag.style.textOverflow = 'ellipsis';
        labelTag.style.maxWidth = '60px';
        labelTag.style.textAlign = 'center';
        labelTag.textContent = labels[idx] || '';

        colGroup.appendChild(valTag);
        colGroup.appendChild(barTrack);
        colGroup.appendChild(labelTag);

        // Tooltip listeners
        colGroup.addEventListener('mouseenter', (e) => {
          barFill.style.filter = 'brightness(1.15)';
          showTooltip(e, `<div><strong>${labels[idx]}</strong>: ${val} ${opts.unit}</div>`);
        });
        colGroup.addEventListener('mousemove', (e) => {
          showTooltip(e, `<div><strong>${labels[idx]}</strong>: ${val} ${opts.unit}</div>`);
        });
        colGroup.addEventListener('mouseleave', () => {
          barFill.style.filter = 'none';
          hideTooltip();
        });

        chartWrap.appendChild(colGroup);

        // Animate bar growth
        const targetPercent = Math.min(100, Math.round((val / maxVal) * 100));
        setTimeout(() => {
          barFill.style.height = `${targetPercent}%`;
          valTag.style.opacity = '1';
        }, 40 + idx * 45);
      });

      container.appendChild(chartWrap);
    },

    /**
     * Render an animated Horizontal Bar Chart.
     * data: [{ label: 'CSE', value: 45, percentage: 65 }, ...]
     */
    renderHorizontalBarChart: function (container, items, options) {
      if (!container) return;
      container.innerHTML = '';

      if (!items || items.length === 0) {
        this.renderEmptyState(container, options && options.emptyMessage);
        return;
      }

      const opts = Object.assign({
        color: '#6366F1',
        unit: ''
      }, options || {});

      const maxVal = Math.max(...items.map(it => it.value || 0), 1);

      const wrap = document.createElement('div');
      wrap.className = 'edubridge-h-bars';
      wrap.style.display = 'flex';
      wrap.style.flexDirection = 'column';
      wrap.style.gap = '0.85rem';
      wrap.style.padding = '0.5rem 0';

      items.forEach((item, idx) => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.flexDirection = 'column';
        row.style.gap = '0.25rem';

        const metaLine = document.createElement('div');
        metaLine.style.display = 'flex';
        metaLine.style.justifyContent = 'space-between';
        metaLine.style.fontSize = '0.825rem';

        const labelSpan = document.createElement('span');
        labelSpan.style.fontWeight = '600';
        labelSpan.style.color = 'var(--text-main)';
        labelSpan.textContent = item.label;

        const valSpan = document.createElement('span');
        valSpan.style.fontWeight = '700';
        valSpan.style.color = opts.color;
        valSpan.textContent = `${item.value} ${opts.unit}`;

        metaLine.appendChild(labelSpan);
        metaLine.appendChild(valSpan);

        const track = document.createElement('div');
        track.style.height = '8px';
        track.style.borderRadius = '999px';
        track.style.background = 'var(--bg-canvas-subtle)';
        track.style.overflow = 'hidden';

        const fill = document.createElement('div');
        fill.style.height = '100%';
        fill.style.width = '0%'; // Start at zero width
        fill.style.borderRadius = '999px';
        fill.style.background = item.color || opts.color;
        fill.style.transition = 'width 0.9s cubic-bezier(0.16, 1, 0.3, 1)';

        track.appendChild(fill);
        row.appendChild(metaLine);
        row.appendChild(track);
        wrap.appendChild(row);

        // Animate fill width
        const pct = Math.min(100, Math.round((item.value / maxVal) * 100));
        setTimeout(() => {
          fill.style.width = `${pct}%`;
        }, 50 + idx * 50);
      });

      container.appendChild(wrap);
    },

    /**
     * Render an animated Line / Area Chart using SVG paths.
     * data: { labels: ['01 Oct', '02 Oct', ...], values: [12, 18, 14, 25, 30] }
     */
    renderLineChart: function (container, data, options) {
      if (!container) return;
      container.innerHTML = '';

      if (!data || !data.values || data.values.length === 0 || data.values.every(v => v === 0)) {
        this.renderEmptyState(container, options && options.emptyMessage);
        return;
      }

      const opts = Object.assign({
        strokeColor: '#3B82F6',
        fillColor: 'rgba(59, 130, 246, 0.12)',
        height: 160,
        unit: 'Points',
        isArea: true
      }, options || {});

      const width = 450;
      const height = opts.height;
      const padding = { top: 20, right: 20, bottom: 30, left: 30 };

      const innerWidth = width - padding.left - padding.right;
      const innerHeight = height - padding.top - padding.bottom;

      const values = data.values;
      const labels = data.labels;
      const maxVal = Math.max(...values, 10);
      const minVal = 0;

      const points = values.map((val, idx) => {
        const x = padding.left + (idx / Math.max(1, values.length - 1)) * innerWidth;
        const y = padding.top + innerHeight - ((val - minVal) / (maxVal - minVal)) * innerHeight;
        return { x, y, val, label: labels[idx] };
      });

      // SVG Element
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.setAttribute('width', '100%');
      svg.setAttribute('height', `${height}px`);
      svg.style.overflow = 'visible';

      // Grids
      for (let g = 0; g <= 3; g++) {
        const gy = padding.top + (innerHeight / 3) * g;
        const gridLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        gridLine.setAttribute('x1', padding.left);
        gridLine.setAttribute('y1', gy);
        gridLine.setAttribute('x2', width - padding.right);
        gridLine.setAttribute('y2', gy);
        gridLine.setAttribute('stroke', '#E2E8F0');
        gridLine.setAttribute('stroke-dasharray', '3 3');
        svg.appendChild(gridLine);
      }

      // Path string
      const pathD = points.reduce((acc, pt, i) => {
        return i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`;
      }, '');

      // Area Path
      if (opts.isArea) {
        const areaD = `${pathD} L ${points[points.length - 1].x} ${padding.top + innerHeight} L ${points[0].x} ${padding.top + innerHeight} Z`;
        const areaPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        areaPath.setAttribute('d', areaD);
        areaPath.setAttribute('fill', opts.fillColor);
        areaPath.style.opacity = '0';
        areaPath.style.transition = 'opacity 0.8s ease';
        svg.appendChild(areaPath);

        setTimeout(() => {
          areaPath.style.opacity = '1';
        }, 300);
      }

      // Main Line Path
      const linePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      linePath.setAttribute('d', pathD);
      linePath.setAttribute('fill', 'none');
      linePath.setAttribute('stroke', opts.strokeColor);
      linePath.setAttribute('stroke-width', '3');
      linePath.setAttribute('stroke-linecap', 'round');
      linePath.setAttribute('stroke-linejoin', 'round');

      svg.appendChild(linePath);

      // Animate line draw via stroke-dashoffset
      const pathLength = linePath.getTotalLength ? linePath.getTotalLength() : 800;
      linePath.style.strokeDasharray = `${pathLength} ${pathLength}`;
      linePath.style.strokeDashoffset = `${pathLength}`;
      linePath.style.transition = 'stroke-dashoffset 1s cubic-bezier(0.16, 1, 0.3, 1)';

      setTimeout(() => {
        linePath.style.strokeDashoffset = '0';
      }, 50);

      // Data Circles & Hover Events
      points.forEach((pt) => {
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', pt.x);
        dot.setAttribute('cy', pt.y);
        dot.setAttribute('r', '4');
        dot.setAttribute('fill', '#FFFFFF');
        dot.setAttribute('stroke', opts.strokeColor);
        dot.setAttribute('stroke-width', '2.5');
        dot.style.cursor = 'pointer';
        dot.style.transformOrigin = `${pt.x}px ${pt.y}px`;
        dot.style.transform = 'scale(0)';
        dot.style.transition = 'transform 0.4s ease 0.6s, r 0.15s ease';

        dot.addEventListener('mouseenter', (e) => {
          dot.setAttribute('r', '6');
          dot.setAttribute('fill', opts.strokeColor);
          showTooltip(e, `<div><strong>${pt.label}</strong>: ${pt.val} ${opts.unit}</div>`);
        });
        dot.addEventListener('mousemove', (e) => {
          showTooltip(e, `<div><strong>${pt.label}</strong>: ${pt.val} ${opts.unit}</div>`);
        });
        dot.addEventListener('mouseleave', () => {
          dot.setAttribute('r', '4');
          dot.setAttribute('fill', '#FFFFFF');
          hideTooltip();
        });

        svg.appendChild(dot);

        setTimeout(() => {
          dot.style.transform = 'scale(1)';
        }, 100);
      });

      // X-Axis Labels Container
      const labelsDiv = document.createElement('div');
      labelsDiv.style.display = 'flex';
      labelsDiv.style.justifyContent = 'space-between';
      labelsDiv.style.padding = '0 10px';
      labelsDiv.style.fontSize = '0.72rem';
      labelsDiv.style.color = 'var(--text-muted)';
      labelsDiv.style.marginTop = '4px';

      // Pick up to 6 evenly spaced labels
      const step = Math.max(1, Math.floor(labels.length / 5));
      labels.forEach((lbl, i) => {
        if (i % step === 0 || i === labels.length - 1) {
          const span = document.createElement('span');
          span.textContent = lbl;
          labelsDiv.appendChild(span);
        }
      });

      container.appendChild(svg);
      container.appendChild(labelsDiv);
    },

    /**
     * Render an animated Donut Chart.
     * segments: [{ label: 'Active', value: 85, color: '#10B981' }, { label: 'Suspended', value: 15, color: '#EF4444' }]
     */
    renderDonutChart: function (container, segments, options) {
      if (!container) return;
      container.innerHTML = '';

      if (!segments || segments.length === 0 || segments.every(s => s.value === 0)) {
        this.renderEmptyState(container, options && options.emptyMessage);
        return;
      }

      const opts = Object.assign({
        size: 160,
        strokeWidth: 6,
        centerText: '',
        centerLabel: ''
      }, options || {});

      const total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 1;
      const radius = 15.91549430918954; // circumference = 100

      const wrap = document.createElement('div');
      wrap.style.display = 'flex';
      wrap.style.alignItems = 'center';
      wrap.style.justifyContent = 'space-around';
      wrap.style.gap = '1.25rem';
      wrap.style.flexWrap = 'wrap';
      wrap.style.padding = '0.5rem 0';

      const svgWrap = document.createElement('div');
      svgWrap.style.position = 'relative';
      svgWrap.style.width = `${opts.size}px`;
      svgWrap.style.height = `${opts.size}px`;
      svgWrap.style.flexShrink = '0';

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 42 42');
      svg.setAttribute('width', `${opts.size}`);
      svg.setAttribute('height', `${opts.size}`);

      // Background ring
      const bgCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      bgCircle.setAttribute('cx', '21');
      bgCircle.setAttribute('cy', '21');
      bgCircle.setAttribute('r', `${radius}`);
      bgCircle.setAttribute('fill', 'transparent');
      bgCircle.setAttribute('stroke', '#F1F5F9');
      bgCircle.setAttribute('stroke-width', `${opts.strokeWidth}`);
      svg.appendChild(bgCircle);

      // Animated segment rings
      let accumulatedPercent = 25; // 12 o'clock start
      segments.forEach((seg, idx) => {
        const segPercent = (seg.value / total) * 100;
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '21');
        circle.setAttribute('cy', '21');
        circle.setAttribute('r', `${radius}`);
        circle.setAttribute('fill', 'transparent');
        circle.setAttribute('stroke', seg.color || PALETTES.multi[idx % PALETTES.multi.length]);
        circle.setAttribute('stroke-width', `${opts.strokeWidth}`);

        // Start dasharray at zero
        circle.setAttribute('stroke-dasharray', `0 100`);
        circle.setAttribute('stroke-dashoffset', `${accumulatedPercent}`);
        circle.style.transition = 'stroke-dasharray 0.9s cubic-bezier(0.16, 1, 0.3, 1)';
        circle.style.cursor = 'pointer';

        circle.addEventListener('mouseenter', (e) => {
          circle.setAttribute('stroke-width', `${opts.strokeWidth + 2}`);
          showTooltip(e, `<div><strong>${seg.label}</strong>: ${seg.value} (${Math.round(segPercent)}%)</div>`);
        });
        circle.addEventListener('mousemove', (e) => {
          showTooltip(e, `<div><strong>${seg.label}</strong>: ${seg.value} (${Math.round(segPercent)}%)</div>`);
        });
        circle.addEventListener('mouseleave', () => {
          circle.setAttribute('stroke-width', `${opts.strokeWidth}`);
          hideTooltip();
        });

        svg.appendChild(circle);

        setTimeout(() => {
          circle.setAttribute('stroke-dasharray', `${segPercent} ${100 - segPercent}`);
        }, 60 + idx * 40);

        accumulatedPercent -= segPercent;
      });

      svgWrap.appendChild(svg);

      // Center Text
      if (opts.centerText) {
        const center = document.createElement('div');
        center.style.position = 'absolute';
        center.style.top = '50%';
        center.style.left = '50%';
        center.style.transform = 'translate(-50%, -50%)';
        center.style.textAlign = 'center';
        center.innerHTML = `
          <div style="font-size: 1.35rem; font-weight: 800; color: var(--text-main); line-height: 1;">${opts.centerText}</div>
          <small style="font-size: 0.685rem; color: var(--text-muted); font-weight: 600;">${opts.centerLabel || ''}</small>
        `;
        svgWrap.appendChild(center);
      }

      wrap.appendChild(svgWrap);

      // Legend
      const legend = document.createElement('div');
      legend.style.display = 'flex';
      legend.style.flexDirection = 'column';
      legend.style.gap = '0.45rem';
      legend.style.fontSize = '0.825rem';
      legend.style.minWidth = '130px';

      segments.forEach((seg, idx) => {
        const segPercent = Math.round((seg.value / total) * 100);
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.justifyContent = 'space-between';
        item.style.gap = '0.75rem';

        const color = seg.color || PALETTES.multi[idx % PALETTES.multi.length];
        item.innerHTML = `
          <span style="display: flex; align-items: center; gap: 0.45rem;">
            <span style="width: 10px; height: 10px; border-radius: 50%; background: ${color}; flex-shrink: 0;"></span>
            <span>${seg.label}</span>
          </span>
          <span style="font-weight: 700; color: var(--text-main); font-family: var(--font-mono);">${seg.value} (${segPercent}%)</span>
        `;
        legend.appendChild(item);
      });

      wrap.appendChild(legend);
      container.appendChild(wrap);
    }
  };

  // Expose globally
  window.EduBridgeCharts = EduBridgeCharts;
  window.Charts = EduBridgeCharts;

})(window, document);
