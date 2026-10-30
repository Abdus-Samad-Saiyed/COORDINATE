# Campus Nexus — Mechanical Zen Engine & Visual Experience

---

## 1. Aesthetic Philosophy & Visual Identity

Campus Nexus uses a technical **clockwork dark-glass** design language:
- **Atmospheric Palette:** OLED-black foundations (`#050B08`), deep emerald translucent glassmorphism (`rgba(11, 22, 18, 0.82)`), and high-contrast typography.
- **Dynamic Accent Colorways:** Preset palettes for Emerald (`#08B74F`), Cyan (`#00D2FF`), Indigo (`#818CF8`), Amber (`#F59E0B`), Rose (`#FB7185`), Purple, Teal, and Orange, plus a Custom Hex Picker.
- **Mechanical Ambient Watermark:** A precision SVG canvas rendered behind content featuring real-time clockwork hands, gear teeth, and interactive mechanical meshes.

---

## 2. Real-Time Clockwork Engine (`static/js/watermark.js`)

### 2.1 Continuous Smooth Clock Hands
The center clock dial (`#clockwork-hands`) rotates synchronously with the client machine's system time:

```javascript
function calculateClockAngles(date) {
  const hours = date.getHours() % 12;
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();
  const millis = date.getMilliseconds();

  const hourAngle = ((hours + (minutes / 60) + (seconds / 3600)) * 30);
  const minuteAngle = ((minutes + (seconds / 60) + (millis / 60000)) * 6);
  const secondAngle = ((seconds + (millis / 1000)) * 6);

  return { hourAngle, minuteAngle, secondAngle };
}
```

- Executed inside `requestAnimationFrame` for 60fps / 120fps fluid motion without jumping or second-hand ticking jerkiness.
- Rotates around SVG center coordinates `(500, 500)`.

### 2.2 Ambient Gear Rotation & Interactive Click Impulses
Edge and corner gears rotate at calibrated differential speeds (`data-speed`).
When the user clicks anywhere on the viewport, an interactive impulse (`gearImpulse += 18`) accelerates the gears temporarily before smoothly decaying back to resting speed.

---

## 3. Goofy Foreground Scatter (Zen Mode)

Activating Zen Mode (via the navbar clock button, the effects menu, or keyboard shortcuts) disperses the foreground interface off-screen to reveal the full mechanical clockwork canvas.

```
[ Normal View: Cards in Grid ]
              |
              | --- User clicks "Zen Mode" ---
              v
[ Staggered Dispersal ]
  Card 1, Card 2, Card 3 fly off-screen on curved trajectories.
              |
              v
[ The Startled Box Mechanism ]
  -> Exactly one card stays completely still for 650ms while everything else departs.
  -> At 650ms: Card realizes it has been left alone!
  -> Wobbles & shakes frantically for 750ms (scale 1.2, rotation ±9deg).
  -> Rockets away into the corner at top speed (155vw, 90vh, 75deg tilt).
              |
              v
[ Pure Mechanical Canvas Revealed ]
  Clockwork watermark glows at 88% opacity.
  #zen-restore-banner floats at bottom ("Bring Everything Back! [Esc]").
```

### 3.1 Restore Mechanics
Pressing the **Escape (`Esc`)** key or clicking the floating **Bring Everything Back!** banner smoothly cascades all cards, boxes, and navbars back into place via easing curves (`cubic-bezier(0.16, 1, 0.3, 1)`).

---

## 4. The Eccentric Light Mode Reluctance Gate

The platform actively discourages eye-straining bright themes through an eccentric multi-stage reluctance dialogue:

```
User clicks "Switch to Light Mode"
          |
          +---> Attempt 1:
          |     Triggers humorous toast: "Really? You want that. No one wants that. 🤨"
          |     Theme remains DARK.
          |
          +---> Attempt 2:
          |     Screen does a brief panic shake.
          |     Triggers toast: "Don't do this to yourself. Stop it weirdo, or embrace the dark side. 🦇"
          |     Theme remains DARK.
          |
          `---> Attempt 3:
                Accepts user's stubborn persistence.
                Switches theme to LIGHT.
                Displays toast: "Suit yourself weirdo. Live with your choices. 🙄"
```

Once unlocked on the third attempt, the preference is saved in `localStorage['nexus_theme'] = 'light'`.

---

## 5. Seamless Inter-Page Zen Transitions

When enabled in visual settings, navigation between platform pages preserves spatial continuity:

1. **Departure:** Clicking any internal link triggers a fast card scatter, holds in Zen Mode, and writes `sessionStorage['nexus_zen_transition_state'] = 'incoming'`.
2. **Transfer:** The browser loads the destination URL.
3. **Arrival:**
   - The destination page's HTML loads with `.zen-incoming-page`.
   - All cards are pre-positioned off-screen with `transition: none` to prevent visual flashes.
   - The page holds in clean Zen Mode for **180ms**.
   - Cards cascade inward into their exact grid positions.
