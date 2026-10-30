/**
 * CAMPUS NEXUS — Clockwork Watermark & Theme Engine
 *
 * 1. Center Clock Hands: Real client system date/time driven (Center: 500, 500)
 *    using requestAnimationFrame for smooth, precise rotation without jumping.
 * 2. Mechanical Gear Shadows: Ambient mechanical rotation at slight, calm speed.
 * 3. Watermark Mode & Opacity: Toggle-able (Both, Gears Only, Clock Only, Off).
 * 4. Light / Dark Theme: Complete application-wide styling transform.
 * 5. Dynamic Accent Palettes: Emerald, Cyan, Indigo, Amber, Rose.
 * 6. Custom Technical Cursor: Follower with spring physics and magnetic hover.
 * 7. Goofy Foreground Scatter: Boxes hilariously disperse off-screen, with a startled
 *    last box that delays, wobbles, and rockets away to reveal the pure clockwork canvas!
 */

(function initClockworkWatermarkAndTheme() {
  'use strict';

  // ------------------------------------------------------------------
  // 1. Clock Calculations & Hand Rotations
  // ------------------------------------------------------------------
  function calculateClockAngles(date) {
    const hours = date.getHours() % 12;
    const minutes = date.getMinutes();
    const seconds = date.getSeconds();
    const millis = date.getMilliseconds();

    // Exact continuous rotation angles (360 degrees full circle)
    const hourAngle = ((hours + (minutes / 60) + (seconds / 3600)) * 30);
    const minuteAngle = ((minutes + (seconds / 60) + (millis / 60000)) * 6);
    const secondAngle = ((seconds + (millis / 1000)) * 6);

    return { hourAngle, minuteAngle, secondAngle };
  }

  function applyHandRotations(hourAngle, minuteAngle, secondAngle) {
    const hourHand = document.getElementById('clockwork-hour-hand');
    const minuteHand = document.getElementById('clockwork-minute-hand');
    const secondHand = document.getElementById('clockwork-second-hand');

    // SVG clock center coordinates: (500, 500)
    if (hourHand) {
      hourHand.setAttribute('transform', `rotate(${hourAngle.toFixed(2)} 500 500)`);
    }
    if (minuteHand) {
      minuteHand.setAttribute('transform', `rotate(${minuteAngle.toFixed(2)} 500 500)`);
    }
    if (secondHand) {
      secondHand.setAttribute('transform', `rotate(${secondAngle.toFixed(2)} 500 500)`);
    }
  }

  // ------------------------------------------------------------------
  // 2. Ambient Gears & Interactive Click Turns
  // ------------------------------------------------------------------
  let gearImpulse = 0;
  let ambientGearAngle = 0;

  function initEdgeGearInteractivity() {
    document.addEventListener('click', function (e) {
      // Dynamic rotational impulse flick when clicking
      gearImpulse += 18;
    });
  }

  // ------------------------------------------------------------------
  // 3. Watermark Mode, Gear Complexity, Spread & Opacity Engine
  // ------------------------------------------------------------------
  function applyWatermarkSettings() {
    const container = document.getElementById('clockwork-watermark');
    if (!container) return;

    const mode = localStorage.getItem('nexus_watermark_mode') || 'both'; // both, gears, clock, off
    const opacity = localStorage.getItem('nexus_watermark_opacity') || '0.22';
    const complexity = localStorage.getItem('nexus_gear_complexity') || 'high'; // low, med, high
    const gearSpread = localStorage.getItem('nexus_gear_spread') || 'constellation'; // constellation, subtle, off

    // Apply Opacity
    container.style.opacity = opacity;

    // Apply Mode to layers
    const clockLayer = document.getElementById('clockwork-layer');
    const gearsLayer = document.getElementById('gears-layer');
    const scatteredLayer = document.getElementById('scattered-gears-layer');
    const midGears = document.querySelectorAll('.gear-edge-l, .gear-edge-r');

    if (mode === 'off') {
      container.style.display = 'none';
    } else {
      container.style.display = 'block';

      if (mode === 'gears') {
        if (clockLayer) clockLayer.style.display = 'none';
        if (gearsLayer) gearsLayer.style.display = '';
        if (scatteredLayer) scatteredLayer.style.display = (gearSpread === 'off') ? 'none' : '';
      } else if (mode === 'clock') {
        if (clockLayer) clockLayer.style.display = '';
        if (gearsLayer) gearsLayer.style.display = 'none';
        if (scatteredLayer) scatteredLayer.style.display = 'none';
      } else { // both
        if (clockLayer) clockLayer.style.display = '';
        if (gearsLayer) gearsLayer.style.display = '';
        if (scatteredLayer) scatteredLayer.style.display = (gearSpread === 'off') ? 'none' : '';
      }

      // Apply Complexity on corner/edge gears
      if (mode !== 'clock' && gearsLayer) {
        if (complexity === 'low') {
          midGears.forEach(g => g.style.display = 'none');
        } else {
          midGears.forEach(g => g.style.display = '');
        }
      }

      // Apply Random Gear Spread across viewport
      if (scatteredLayer && mode !== 'clock') {
        if (gearSpread === 'off') {
          scatteredLayer.style.display = 'none';
        } else {
          scatteredLayer.style.display = '';
          const denseGears = scatteredLayer.querySelectorAll('.scatter-dense');
          if (gearSpread === 'subtle') {
            denseGears.forEach(g => g.style.display = 'none');
          } else {
            denseGears.forEach(g => g.style.display = '');
          }
        }
      }
    }

    // Sync UI elements if present
    const opacitySlider = document.getElementById('fx-opacity-slider');
    const opacityValLabel = document.getElementById('fx-opacity-val');
    if (opacitySlider) opacitySlider.value = Math.round(parseFloat(opacity) * 100);
    if (opacityValLabel) opacityValLabel.textContent = `${Math.round(parseFloat(opacity) * 100)}%`;

    const modeSelect = document.getElementById('fx-watermark-mode');
    if (modeSelect) modeSelect.value = mode;

    const compSelect = document.getElementById('fx-gear-complexity');
    if (compSelect) compSelect.value = complexity;

    const spreadSelect = document.getElementById('fx-gear-spread');
    if (spreadSelect) spreadSelect.value = gearSpread;

    const spreadBadge = document.getElementById('fx-gear-spread-badge');
    if (spreadBadge) {
      if (gearSpread === 'constellation') {
        spreadBadge.textContent = 'Constellation';
        spreadBadge.className = 'badge bg-success-subtle green-accent px-2 py-0.5';
      } else if (gearSpread === 'subtle') {
        spreadBadge.textContent = 'Subtle';
        spreadBadge.className = 'badge bg-info-subtle text-info px-2 py-0.5';
      } else {
        spreadBadge.textContent = 'Off';
        spreadBadge.className = 'badge bg-secondary-subtle text-secondary px-2 py-0.5';
      }
    }

    // Sync Zen Page Transitions Switch
    const zenTransitionsSwitch = document.getElementById('fx-zen-transitions-switch');
    if (zenTransitionsSwitch) {
      const zenTransitionsEnabled = localStorage.getItem('nexus_zen_transitions') !== 'false';
      zenTransitionsSwitch.checked = zenTransitionsEnabled;
    }
  }

  window.setNexusZenTransitions = function (enabled) {
    localStorage.setItem('nexus_zen_transitions', enabled ? 'true' : 'false');
    const zenTransitionsSwitch = document.getElementById('fx-zen-transitions-switch');
    if (zenTransitionsSwitch) {
      zenTransitionsSwitch.checked = !!enabled;
    }
  };

  window.setNexusWatermarkMode = function (mode) {
    localStorage.setItem('nexus_watermark_mode', mode);
    applyWatermarkSettings();
  };

  window.setNexusWatermarkOpacity = function (percent) {
    const val = (Math.max(0, Math.min(60, parseInt(percent, 10))) / 100).toFixed(2);
    localStorage.setItem('nexus_watermark_opacity', val);
    applyWatermarkSettings();
  };

  window.setNexusGearComplexity = function (level) {
    localStorage.setItem('nexus_gear_complexity', level);
    applyWatermarkSettings();
  };

  window.setNexusGearSpread = function (spread) {
    localStorage.setItem('nexus_gear_spread', spread);
    applyWatermarkSettings();
  };

  window.toggleClockworkWatermark = function () {
    const current = localStorage.getItem('nexus_watermark_mode') || 'both';
    const next = (current === 'off') ? 'both' : 'off';
    localStorage.setItem('nexus_watermark_mode', next);
    applyWatermarkSettings();
  };

  // ------------------------------------------------------------------
  // 4. Light / Dark Theme Switcher
  // ------------------------------------------------------------------
  function applyNexusTheme(theme) {
    const selected = theme || localStorage.getItem('nexus_theme') || 'dark';
    document.documentElement.setAttribute('data-bs-theme', selected);
    document.documentElement.setAttribute('data-theme', selected);
    localStorage.setItem('nexus_theme', selected);

    const icons = document.querySelectorAll('#theme-toggle-icon, .theme-toggle-icon');
    icons.forEach(icon => {
      if (selected === 'light') {
        icon.className = 'bi bi-moon-stars-fill text-primary theme-toggle-icon';
      } else {
        icon.className = 'bi bi-sun-fill text-warning theme-toggle-icon';
      }
    });

    // If custom accent is active, recalculate theme-dependent backgrounds
    const currentAccent = localStorage.getItem('nexus_accent') || 'emerald';
    if (currentAccent === 'custom') {
      const storedHex = localStorage.getItem('nexus_custom_hex') || '#08B74F';
      window.setNexusCustomHex(storedHex, true);
    } else {
      applyNexusAccent(currentAccent);
    }
  }

  // ------------------------------------------------------------------
  // Eccentric Theme Switcher with 4-Attempt Resistance Easter Egg
  // ------------------------------------------------------------------
  function showEccentricToast(message, icon = 'bi-exclamation-diamond-fill', duration = 4000) {
    let toast = document.getElementById('eccentric-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'eccentric-toast';
      toast.style.cssText = `
        position: fixed;
        top: 24px;
        left: 50%;
        transform: translateX(-50%) translateY(-24px);
        z-index: 999999;
        background: rgba(14, 18, 24, 0.94);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border: 1px solid rgba(245, 158, 11, 0.6);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7), 0 0 24px rgba(245, 158, 11, 0.25);
        color: #fff;
        padding: 12px 26px;
        border-radius: 9999px;
        font-size: 0.95rem;
        font-weight: 600;
        letter-spacing: 0.2px;
        display: flex;
        align-items: center;
        gap: 12px;
        opacity: 0;
        pointer-events: none;
        transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.35s ease;
      `;
      document.body.appendChild(toast);
    }

    toast.innerHTML = '';
    const toastIcon = document.createElement('i');
    toastIcon.className = `bi ${icon} text-warning fs-5`;
    const toastMsg = document.createElement('span');
    toastMsg.textContent = message;
    toast.appendChild(toastIcon);
    toast.appendChild(toastMsg);
    requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(-50%) translateY(0)';
      toast.style.pointerEvents = 'auto';
    });

    if (toast._timer) clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(-50%) translateY(-24px)';
      toast.style.pointerEvents = 'none';
    }, duration);
  }

  let lightModeAttempts = parseInt(sessionStorage.getItem('nexus_light_attempts') || '0', 10);

  window.toggleNexusTheme = function () {
    const current = document.documentElement.getAttribute('data-bs-theme') || 'dark';

    // Animate wobble on theme toggle button(s)
    const btns = document.querySelectorAll('#theme-toggle-btn, .theme-toggle-btn');
    btns.forEach(btn => {
      btn.classList.remove('theme-wobble');
      void btn.offsetWidth;
      btn.classList.add('theme-wobble');
    });

    if (current === 'light') {
      // Switching back to dark mode is always welcomed and immediate
      lightModeAttempts = 0;
      sessionStorage.setItem('nexus_light_attempts', '0');
      applyNexusTheme('dark');
      showEccentricToast('Welcome back to sanity!', 'bi-moon-stars-fill', 3500);
      return;
    }

    // Student attempting to switch from dark to light mode
    lightModeAttempts += 1;
    sessionStorage.setItem('nexus_light_attempts', lightModeAttempts.toString());

    if (lightModeAttempts === 1) {
      showEccentricToast("Really dude!?", 'bi-question-diamond-fill', 3800);
    } else if (lightModeAttempts === 2) {
      showEccentricToast("Embrace the dark side!", 'bi-moon-stars-fill', 3800);
    } else if (lightModeAttempts === 3) {
      showEccentricToast("Don't do that weirdo!", 'bi-emoji-dizzy-fill', 3800);
    } else {
      // 4th attempt: Let them go into light mode
      lightModeAttempts = 0;
      sessionStorage.setItem('nexus_light_attempts', '0');
      applyNexusTheme('light');
      showEccentricToast("You asked for it; now live with your choices!", 'bi-sun-fill', 4500);
    }
  };

  // ------------------------------------------------------------------
  // 5. Multiple Color Profiles & Custom Hex Picker
  // ------------------------------------------------------------------
  const PRESET_HEX_MAP = {
    emerald: '#08B74F',
    cyan: '#00D2FF',
    indigo: '#818CF8',
    amber: '#F59E0B',
    rose: '#FB7185',
    purple: '#A855F7',
    teal: '#14B8A6',
    orange: '#FF6B2B'
  };

  window.setNexusCustomHex = function (rawHex, preserveState) {
    if (!rawHex) return;
    let hex = rawHex.trim();
    if (!hex.startsWith('#')) hex = '#' + hex;
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;

    hex = hex.toUpperCase();
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    const root = document.documentElement;
    const isLight = root.getAttribute('data-bs-theme') === 'light';

    root.style.setProperty('--green', hex);
    root.style.setProperty('--green-hover', hex);
    root.style.setProperty('--green-dim', `rgba(${r}, ${g}, ${b}, 0.14)`);
    root.style.setProperty('--green-glow', `rgba(${r}, ${g}, ${b}, 0.32)`);
    root.style.setProperty('--shadow-green', `0 0 24px rgba(${r}, ${g}, ${b}, 0.22)`);
    root.style.setProperty('--border-hover', `rgba(${r}, ${g}, ${b}, 0.45)`);
    root.style.setProperty('--glass-border', `rgba(${r}, ${g}, ${b}, 0.22)`);

    if (isLight) {
      root.style.setProperty('--bg', '#f8fafc');
      root.style.setProperty('--bg-gradient', `radial-gradient(ellipse 80% 50% at 50% -10%, rgba(${r}, ${g}, ${b}, 0.10), transparent 70%)`);
      root.style.setProperty('--glass-bg', '#ffffff');
    } else {
      root.style.setProperty('--bg', `rgb(${Math.round(r * 0.05)}, ${Math.round(g * 0.05)}, ${Math.round(b * 0.05)})`);
      root.style.setProperty('--bg-gradient', `radial-gradient(ellipse 80% 50% at 50% -10%, rgba(${r}, ${g}, ${b}, 0.18), transparent 70%)`);
      root.style.setProperty('--glass-bg', `rgba(${Math.round(r * 0.10 + 10)}, ${Math.round(g * 0.10 + 10)}, ${Math.round(b * 0.10 + 10)}, 0.82)`);
    }

    root.setAttribute('data-accent', 'custom');
    if (!preserveState) {
      localStorage.setItem('nexus_accent', 'custom');
      localStorage.setItem('nexus_custom_hex', hex);
    }

    // Sync input controls
    const picker = document.getElementById('fx-custom-hex-picker');
    const input = document.getElementById('fx-custom-hex-input');
    const label = document.getElementById('fx-hex-label');
    if (picker) picker.value = hex;
    if (input) input.value = hex;
    if (label) label.textContent = hex;
  };

  function applyNexusAccent(accent) {
    const selected = accent || localStorage.getItem('nexus_accent') || 'emerald';

    if (selected === 'custom') {
      const hex = localStorage.getItem('nexus_custom_hex') || '#08B74F';
      window.setNexusCustomHex(hex);
      return;
    }

    // Clear dynamic inline style overrides so preset CSS takes effect
    const root = document.documentElement;
    const dynamicProps = [
      '--green', '--green-hover', '--green-dim', '--green-glow',
      '--shadow-green', '--border-hover', '--glass-border',
      '--bg', '--bg-gradient', '--glass-bg'
    ];
    dynamicProps.forEach(prop => root.style.removeProperty(prop));

    root.setAttribute('data-accent', selected);
    localStorage.setItem('nexus_accent', selected);

    // Sync custom picker with preset color
    const presetHex = PRESET_HEX_MAP[selected] || '#08B74F';
    const picker = document.getElementById('fx-custom-hex-picker');
    const input = document.getElementById('fx-custom-hex-input');
    const label = document.getElementById('fx-hex-label');
    if (picker) picker.value = presetHex;
    if (input) input.value = presetHex;
    if (label) label.textContent = presetHex;
  }

  window.setNexusAccent = function (accent) {
    applyNexusAccent(accent);
  };

  // ------------------------------------------------------------------
  // 6. Custom Sleek Technical Cursor Follower
  // ------------------------------------------------------------------
  function initTechnicalCursor() {
    if (!window.matchMedia || !window.matchMedia('(pointer: fine)').matches) {
      return;
    }

    const cursorSetting = localStorage.getItem('nexus_cursor') || 'magnetic';
    if (cursorSetting === 'off') {
      document.body.classList.add('nexus-cursor-disabled');
      return;
    }

    let dot = document.querySelector('.nexus-cursor-dot');
    let ring = document.querySelector('.nexus-cursor-ring');

    if (!dot) {
      dot = document.createElement('div');
      dot.className = 'nexus-cursor-dot';
      document.body.appendChild(dot);
    }

    if (!ring) {
      ring = document.createElement('div');
      ring.className = 'nexus-cursor-ring';
      document.body.appendChild(ring);
    }

    let mouseX = -100;
    let mouseY = -100;
    let ringX = -100;
    let ringY = -100;
    let targetX = -100;
    let targetY = -100;
    let magneticTarget = null;

    window.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      dot.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0) translate(-50%, -50%)`;

      if (magneticTarget) {
        const rect = magneticTarget.getBoundingClientRect();
        targetX = rect.left + rect.width / 2;
        targetY = rect.top + rect.height / 2;
      } else {
        targetX = mouseX;
        targetY = mouseY;
      }
    });

    function renderCursor() {
      const ease = magneticTarget ? 0.25 : 0.18;
      ringX += (targetX - ringX) * ease;
      ringY += (targetY - ringY) * ease;
      ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0) translate(-50%, -50%)`;
      requestAnimationFrame(renderCursor);
    }
    requestAnimationFrame(renderCursor);

    window.addEventListener('mousedown', function (e) {
      ring.classList.add('cursor-active');
      const ripple = document.createElement('div');
      ripple.className = 'nexus-cursor-ripple';
      ripple.style.left = `${e.clientX}px`;
      ripple.style.top = `${e.clientY}px`;
      document.body.appendChild(ripple);
      setTimeout(() => ripple.remove(), 450);
    });

    window.addEventListener('mouseup', function () {
      ring.classList.remove('cursor-active');
    });

    document.addEventListener('mouseover', function (e) {
      const target = e.target.closest('a, button, .btn, .date-btn, .form-check-input, .dropdown-item');
      if (target) {
        ring.classList.add('cursor-hover');
        if (target.classList.contains('btn') || target.classList.contains('date-btn') || target.tagName === 'BUTTON') {
          magneticTarget = target;
        }
      }
    });

    document.addEventListener('mouseout', function (e) {
      const target = e.target.closest('a, button, .btn, .date-btn, .form-check-input, .dropdown-item');
      if (target) {
        ring.classList.remove('cursor-hover');
        if (magneticTarget === target) {
          magneticTarget = null;
        }
      }
    });
  }

  // ------------------------------------------------------------------
  // 7. Goofy Foreground Scatter ("Zen Clock Reveal")
  // ------------------------------------------------------------------
  let isForegroundScattered = false;
  let startledTimeoutId = null;
  let activeWobbleAnim = null;

  function getScatterTargets() {
    const main = document.querySelector('main.main-content');
    if (!main) return [];

    const targets = [];
    const containers = Array.from(main.querySelectorAll('.container, .container-fluid'));

    if (containers.length === 0) {
      Array.from(main.children).forEach(child => targets.push(child));
    } else {
      containers.forEach(container => {
        Array.from(container.children).forEach(section => {
          // If section is a standard row of column cards (without its own glass/card container wrapper)
          if (section.matches('.row') && !section.classList.contains('glass') && !section.classList.contains('card')) {
            Array.from(section.children).forEach(col => {
              const card = col.querySelector('.glass, .card') || col;
              targets.push(card);
            });
          } else {
            // Direct composite card (e.g. Campus Utilities div.glass.p-4.mt-4),
            // welcome banner, form, or section block: keep UNIFIED so nothing is left behind!
            targets.push(section);
          }
        });
      });
    }

    // Deduplicate and filter out restore banner or watermark
    let uniqueTargets = Array.from(new Set(targets)).filter(el => {
      if (!el || typeof el.closest !== 'function') return false;
      return !el.closest('#zen-restore-banner') && !el.closest('.clockwork-watermark-container');
    });

    // Ensure no element is contained inside another target element (keep only the topmost container)
    uniqueTargets = uniqueTargets.filter(el => {
      return !uniqueTargets.some(other => other !== el && other.contains(el));
    });

    // Also include footer at the very end
    const footer = document.querySelector('footer.footer-custom');
    if (footer && !uniqueTargets.includes(footer)) {
      uniqueTargets.push(footer);
    }

    return uniqueTargets;
  }

  window.toggleForegroundScatter = function () {
    isForegroundScattered = !isForegroundScattered;
    const body = document.body;
    const restoreBanner = document.getElementById('zen-restore-banner');
    const navbar = document.querySelector('.navbar-custom');
    const watermark = document.getElementById('clockwork-watermark');

    // Close any open Bootstrap dropdowns
    document.querySelectorAll('.dropdown-menu.show').forEach(m => m.classList.remove('show'));
    document.querySelectorAll('.dropdown-toggle.show').forEach(b => {
      b.classList.remove('show');
      b.setAttribute('aria-expanded', 'false');
    });

    if (startledTimeoutId) {
      clearTimeout(startledTimeoutId);
      startledTimeoutId = null;
    }
    if (activeWobbleAnim) {
      activeWobbleAnim.cancel();
      activeWobbleAnim = null;
    }

    const targets = getScatterTargets();
    // Calibrated, comical, slow floating trajectories (1600ms - 1950ms)
    const trajectories = [
      { transform: 'translate(-145vw, -20vh) rotate(-38deg) scale(0.72)', duration: 1750 },
      { transform: 'translate(145vw, 18vh) rotate(40deg) scale(0.72)', duration: 1800 },
      { transform: 'translate(15vw, -145vh) rotate(-28deg) scale(0.68)', duration: 1650 },
      { transform: 'translate(-20vw, 145vh) rotate(30deg) scale(0.68)', duration: 1900 },
      { transform: 'translate(135vw, -125vh) rotate(55deg) scale(0.65)', duration: 1850 },
      { transform: 'translate(-135vw, 125vh) rotate(-52deg) scale(0.65)', duration: 1950 },
    ];

    if (isForegroundScattered) {
      body.classList.add('foreground-scattered');
      if (restoreBanner) {
        restoreBanner.classList.add('active');
        restoreBanner.style.opacity = '1';
        restoreBanner.style.pointerEvents = 'auto';
        restoreBanner.style.transform = 'translateX(-50%) translateY(0)';
      }

      if (navbar) {
        navbar.style.transition = 'transform 1.1s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.9s ease';
        navbar.style.transform = 'translateY(-92%)';
        navbar.style.opacity = '0.2';
      }

      if (watermark) {
        watermark.style.opacity = '0.88';
        watermark.style.filter = 'drop-shadow(0 0 24px var(--green-glow, rgba(8, 183, 79, 0.45)))';
      }

      const total = targets.length;
      // Startled box: pick the last prominent card before the footer
      const startledIndex = total > 2 ? total - 2 : total - 1;

      targets.forEach((el, index) => {
        if (index === startledIndex && total > 1) {
          // The STARTLED box: stays put calmly for 650ms while everyone else departs,
          // then realizes it's alone, shakes/wobbles for 750ms, and rockets away!
          el.style.transition = 'none';
          el.style.transform = 'none';
          el.style.opacity = '1';

          startledTimeoutId = setTimeout(() => {
            if (!isForegroundScattered) return;
            try {
              activeWobbleAnim = el.animate([
                { transform: 'scale(1) rotate(0deg)' },
                { transform: 'scale(1.12) rotate(-9deg)' },
                { transform: 'scale(1.14) rotate(9deg)' },
                { transform: 'scale(1.18) rotate(-7deg)' },
                { transform: 'scale(1.20) rotate(7deg)' },
                { transform: 'scale(1.08) rotate(0deg)' }
              ], {
                duration: 750,
                easing: 'ease-in-out',
                iterations: 1,
                fill: 'forwards'
              });
            } catch (err) {}

            // Rockets off-screen late (at 1450ms from scatter click)
            startledTimeoutId = setTimeout(() => {
              if (!isForegroundScattered) return;
              el.style.transition = 'transform 0.85s cubic-bezier(0.7, 0, 0.9, 0.2), opacity 0.65s ease';
              el.style.transform = 'translate(155vw, 90vh) rotate(75deg) scale(0.3)';
              el.style.opacity = '0';
              el.style.pointerEvents = 'none';
            }, 800);
          }, 650);
        } else {
          // Comical parallel & staggered exit (calibrated at 140ms per step)
          const traj = trajectories[index % trajectories.length];
          const delay = (index % 6) * 140;
          el.style.transition = `transform ${traj.duration}ms cubic-bezier(0.35, -0.15, 0.35, 1.25) ${delay}ms, opacity 900ms ease ${delay}ms`;
          el.style.transform = traj.transform;
          el.style.opacity = '0';
          el.style.pointerEvents = 'none';
        }
      });
    } else {
      // Bring everything back smoothly
      body.classList.remove('foreground-scattered');
      if (restoreBanner) {
        restoreBanner.classList.remove('active');
        restoreBanner.style.opacity = '0';
        restoreBanner.style.pointerEvents = 'none';
        restoreBanner.style.transform = 'translateX(-50%) translateY(100px)';
      }

      if (navbar) {
        navbar.style.transform = '';
        navbar.style.opacity = '';
      }

      if (watermark) {
        applyWatermarkSettings();
      }

      targets.forEach(el => {
        el.style.transition = 'transform 0.75s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.55s ease';
        el.style.transform = '';
        el.style.opacity = '';
        el.style.pointerEvents = '';
        setTimeout(() => {
          el.style.transition = '';
        }, 800);
      });
    }
  };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isForegroundScattered) {
      window.toggleForegroundScatter();
    }
  });

  // ------------------------------------------------------------------
  // 8. Zen Page Transitions (Seamless Scatter -> Hold -> Restore)
  // ------------------------------------------------------------------
  let isNavigatingTransition = false;
  let transitionPanickingTimeout = null;
  let transitionPanickingTimeout2 = null;
  let activeTransitionWobble = null;

  const transitionTrajectories = [
    { transform: 'translate(-125vw, -18vh) rotate(-30deg) scale(0.72)', duration: 440 },
    { transform: 'translate(125vw, 15vh) rotate(32deg) scale(0.72)', duration: 460 },
    { transform: 'translate(12vw, -125vh) rotate(-22deg) scale(0.70)', duration: 420 },
    { transform: 'translate(-15vw, 125vh) rotate(25deg) scale(0.70)', duration: 470 },
    { transform: 'translate(115vw, -105vh) rotate(45deg) scale(0.68)', duration: 450 },
    { transform: 'translate(-115vw, 105vh) rotate(-42deg) scale(0.68)', duration: 480 },
  ];

  function handleIncomingZenTransition() {
    const isIncoming = sessionStorage.getItem('nexus_zen_transition_state') === 'incoming';
    if (!isIncoming) {
      document.documentElement.classList.remove('zen-incoming-page');
      return;
    }

    // Immediately consume flag so normal reloads do not re-trigger
    sessionStorage.removeItem('nexus_zen_transition_state');

    const targets = getScatterTargets();
    const navbar = document.querySelector('.navbar-custom');
    const watermark = document.getElementById('clockwork-watermark');

    // 1. Pre-position all targets off-screen with NO transition to prevent any flash
    targets.forEach((el, index) => {
      const traj = transitionTrajectories[index % transitionTrajectories.length];
      el.style.transition = 'none';
      el.style.transform = traj.transform;
      el.style.opacity = '0';
      el.style.pointerEvents = 'none';
    });

    if (navbar) {
      navbar.style.transition = 'none';
      navbar.style.transform = 'translateY(-92%)';
      navbar.style.opacity = '0.2';
    }

    if (watermark) {
      watermark.style.opacity = '0.88';
      watermark.style.filter = 'drop-shadow(0 0 24px var(--green-glow, rgba(8, 183, 79, 0.45)))';
    }

    // Force browser reflow to lock in the scattered inline transforms
    void document.body.offsetHeight;

    // Remove pre-hide class now that inline styles seamlessly sustain the Zen Mode
    document.documentElement.classList.remove('zen-incoming-page');

    // 2. Crisp, brief hold on arrival (~180ms) so spatial continuity is felt without sluggishness
    setTimeout(() => {
      // 3. Smoothly exit Zen Mode: bring navbar down, restore watermark, and cascade cards into place
      if (navbar) {
        navbar.style.transition = 'transform 0.65s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.5s ease';
        navbar.style.transform = '';
        navbar.style.opacity = '';
      }

      if (watermark) {
        applyWatermarkSettings();
      }

      targets.forEach((el, index) => {
        const delay = Math.min(index * 45, 260);
        el.style.transition = `transform 0.7s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, opacity 0.5s ease ${delay}ms`;
        el.style.transform = '';
        el.style.opacity = '';
        el.style.pointerEvents = '';
        setTimeout(() => {
          el.style.transition = '';
        }, 750 + delay);
      });

      isForegroundScattered = false;
    }, 180);
  }

  function initZenPageTransitions() {
    document.addEventListener('click', function (e) {
      // Left click only, without modifier keys
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      // Check if user has enabled Zen Page Transitions (default: true)
      if (localStorage.getItem('nexus_zen_transitions') === 'false') return;

      const anchor = e.target.closest('a');
      if (!anchor) return;

      // Skip non-navigating links or new tab triggers
      if (anchor.target && anchor.target !== '_self') return;
      if (anchor.hasAttribute('download')) return;
      if (anchor.hasAttribute('data-bs-toggle') || anchor.hasAttribute('data-bs-target')) return;

      const rawHref = anchor.getAttribute('href');
      if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:') || rawHref.startsWith('mailto:') || rawHref.startsWith('tel:')) return;

      // Only same-origin navigation
      if (anchor.origin !== window.location.origin) return;

      // Skip if anchor points to exact current URL
      if (anchor.href === window.location.href) return;

      // Skip file downloads or non-HTML API endpoints
      const pathname = anchor.pathname;
      if (pathname.includes('/operations/export/') || pathname.startsWith('/api/')) return;

      // Avoid double triggering
      if (isNavigatingTransition) {
        e.preventDefault();
        return;
      }

      e.preventDefault();
      isNavigatingTransition = true;

      // Close open Bootstrap dropdowns
      document.querySelectorAll('.dropdown-menu.show').forEach(m => m.classList.remove('show'));
      document.querySelectorAll('.dropdown-toggle.show').forEach(b => {
        b.classList.remove('show');
        b.setAttribute('aria-expanded', 'false');
      });

      const targets = getScatterTargets();
      const navbar = document.querySelector('.navbar-custom');
      const watermark = document.getElementById('clockwork-watermark');

      // 1. Enter Zen Mode on Departure: navbar glides up, clockwork watermark brightens
      if (navbar) {
        navbar.style.transition = 'transform 0.65s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.5s ease';
        navbar.style.transform = 'translateY(-92%)';
        navbar.style.opacity = '0.2';
      }

      if (watermark) {
        watermark.style.opacity = '0.88';
        watermark.style.filter = 'drop-shadow(0 0 24px var(--green-glow, rgba(8, 183, 79, 0.45)))';
      }

      const total = targets.length;
      // Startled / hesitant box: pick the last prominent box before the footer
      const hesitantIndex = total > 2 ? total - 2 : total - 1;

      targets.forEach((el, index) => {
        if (index === hesitantIndex && total > 1) {
          // The HESITANT box: freezes completely for 160ms, wondering where everyone went...
          el.style.transition = 'none';
          el.style.transform = 'none';
          el.style.opacity = '1';

          transitionPanickingTimeout = setTimeout(() => {
            if (!isNavigatingTransition) return;
            // Realizes it's alone: frantic, comical panic wobble for 220ms!
            try {
              activeTransitionWobble = el.animate([
                { transform: 'scale(1) rotate(0deg)' },
                { transform: 'scale(1.10) rotate(-8deg)' },
                { transform: 'scale(1.15) rotate(8deg)' },
                { transform: 'scale(1.12) rotate(-6deg)' },
                { transform: 'scale(1.08) rotate(6deg)' },
                { transform: 'scale(1) rotate(0deg)' }
              ], {
                duration: 220,
                easing: 'ease-in-out',
                iterations: 1,
                fill: 'forwards'
              });
            } catch (err) {}

            // Panicky rocket exit off-screen!
            transitionPanickingTimeout2 = setTimeout(() => {
              if (!isNavigatingTransition) return;
              el.style.transition = 'transform 0.36s cubic-bezier(0.7, 0, 0.9, 0.2), opacity 0.28s ease';
              el.style.transform = 'translate(145vw, 85vh) rotate(70deg) scale(0.32)';
              el.style.opacity = '0';
              el.style.pointerEvents = 'none';
            }, 230);
          }, 160);
        } else {
          // Snappy, comical scatter for other cards (duration ~440ms, slight stagger)
          const traj = transitionTrajectories[index % transitionTrajectories.length];
          const delay = (index % 4) * 30;
          el.style.transition = `transform ${traj.duration}ms cubic-bezier(0.35, -0.15, 0.35, 1.25) ${delay}ms, opacity 360ms ease ${delay}ms`;
          el.style.transform = traj.transform;
          el.style.opacity = '0';
          el.style.pointerEvents = 'none';
        }
      });

      // 2. Set incoming state for destination page
      sessionStorage.setItem('nexus_zen_transition_state', 'incoming');

      // 3. Crisp Zen hold: panicking box rockets out by ~650ms,
      //    then hold in pure clockwork Zen for ~230ms before navigating (total ~880ms)
      setTimeout(() => {
        window.location.href = anchor.href;
      }, 880);
    });

    // Reset if restored from bfcache or back button
    window.addEventListener('pageshow', function (event) {
      isNavigatingTransition = false;
      if (transitionPanickingTimeout) clearTimeout(transitionPanickingTimeout);
      if (transitionPanickingTimeout2) clearTimeout(transitionPanickingTimeout2);
      if (activeTransitionWobble) activeTransitionWobble.cancel();
      document.documentElement.classList.remove('zen-incoming-page');
    });
  }

  // ------------------------------------------------------------------
  // Engine Lifecycle & Animation Loop
  // ------------------------------------------------------------------
  function startEngine() {
    // Initial theme, accent & watermark state
    applyNexusTheme();
    applyNexusAccent();
    applyWatermarkSettings();
    initEdgeGearInteractivity();
    initTechnicalCursor();

    // Zen Page Transitions
    handleIncomingZenTransition();
    initZenPageTransitions();

    const reducedMotionQuery = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
    const prefersReducedMotion = reducedMotionQuery ? reducedMotionQuery.matches : false;

    // Smooth real-time clock and ambient slight-speed mechanical gear loop
    function animateLoop() {
      const now = new Date();
      const angles = calculateClockAngles(now);
      applyHandRotations(angles.hourAngle, angles.minuteAngle, angles.secondAngle);

      // Mechanical gear shadows spin at realistic gear ratios with click impulse inertia
      gearImpulse *= 0.95;
      ambientGearAngle += 0.035 + (gearImpulse * 0.04);

      const allGears = document.querySelectorAll('.gear-edge');
      allGears.forEach(function (gear, idx) {
        const cx = gear.getAttribute('data-cx');
        const cy = gear.getAttribute('data-cy');
        const speed = parseFloat(gear.getAttribute('data-speed') || ((idx % 2 === 0) ? '1' : '-1'));
        const totalAngle = ambientGearAngle * speed;

        if (cx && cy) {
          gear.setAttribute('transform', `rotate(${totalAngle.toFixed(2)} ${cx} ${cy})`);
        } else {
          gear.style.transform = `rotate(${totalAngle.toFixed(2)}deg)`;
        }
      });

      if (!prefersReducedMotion) {
        requestAnimationFrame(animateLoop);
      }
    }

    if (prefersReducedMotion) {
      const now = new Date();
      const angles = calculateClockAngles(now);
      applyHandRotations(angles.hourAngle, angles.minuteAngle, angles.secondAngle);
      setInterval(function () {
        const d = new Date();
        const a = calculateClockAngles(d);
        applyHandRotations(a.hourAngle, a.minuteAngle, a.secondAngle);
      }, 1000);
    } else {
      requestAnimationFrame(animateLoop);
    }
  }

  if (typeof window !== 'undefined') {
    window.__campusNexusClockwork = {
      calculateClockAngles: calculateClockAngles,
      applyHandRotations: applyHandRotations,
      setNexusAccent: applyNexusAccent,
      applyNexusTheme: applyNexusTheme,
      toggleForegroundScatter: window.toggleForegroundScatter,
      setNexusZenTransitions: window.setNexusZenTransitions,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startEngine);
  } else {
    startEngine();
  }
})();
