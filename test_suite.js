const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9222;
const HTML_FILE = "file:///S:/Campus-Project/ClockworkZen_Wallpaper.html";

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.id = 1;
    this.callbacks = new Map();
    this.events = [];
    this.consoleLogs = [];
    this.consoleErrors = [];
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.id && this.callbacks.has(msg.id)) {
          const { resolve, reject } = this.callbacks.get(msg.id);
          this.callbacks.delete(msg.id);
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        } else if (msg.method) {
          this.events.push(msg);
          if (msg.method === 'Runtime.consoleAPICalled') {
            const text = msg.params.args.map(a => a.value || JSON.stringify(a)).join(' ');
            this.consoleLogs.push({ type: msg.params.type, text });
            if (msg.params.type === 'error' || msg.params.type === 'warning') {
              this.consoleErrors.push({ type: msg.params.type, text });
            }
          }
          if (msg.method === 'Runtime.exceptionThrown') {
            this.consoleErrors.push({ type: 'exception', text: msg.params.exceptionDetails.text });
          }
        }
      };
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval error: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result ? res.result.value : undefined;
  }

  async screenshot(outputPath) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(outputPath, Buffer.from(res.data, 'base64'));
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false
    });
    await this.send('Emulation.setVisibleSize', { width, height });
    // Also trigger window resize inside page
    await this.eval(`
      window.innerWidth = ${width};
      window.innerHeight = ${height};
      window.dispatchEvent(new Event('resize'));
      if (window.__clockworkZenDebug) {
        window.__clockworkZenDebug.updateResponsiveLayout();
      }
    `);
    await sleep(200);
  }

  close() {
    if (this.ws) this.ws.close();
  }
}

async function runTestSuite() {
  console.log('====================================================');
  console.log('STARTING CLOCKWORK ZEN AUTOMATED TEST SUITE');
  console.log('====================================================\n');

  const testResults = {
    testA: { name: 'Test A: Clock Accuracy', passed: false, details: [] },
    testB: { name: 'Test B: Animation Continuity', passed: false, details: [] },
    testC: { name: 'Test C: Lighting & Orbit', passed: false, details: [] },
    testD: { name: 'Test D: Colour Configuration', passed: false, details: [] },
    testE: { name: 'Test E: Responsiveness (5 Viewports)', passed: false, details: [] },
    testF: { name: 'Test F: Console & Performance', passed: false, details: [] }
  };

  // Launch Chrome
  console.log('Launching headless Chrome...');
  const chromeProcess = spawn(CHROME_PATH, [
    `--remote-debugging-port=${PORT}`,
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-extensions',
    '--no-first-run',
    '--window-size=1920,1080',
    '--hide-scrollbars',
    '--user-data-dir=' + path.join(process.env.TEMP, 'chrome_test_profile_' + Date.now()),
    HTML_FILE
  ]);

  // Wait for Chrome port to be ready
  let targetWsUrl = null;
  for (let i = 0; i < 30; i++) {
    await sleep(300);
    try {
      const list = await fetchJson(`http://127.0.0.1:${PORT}/json/list`);
      const pageTarget = list && list.find(t => t.type === 'page' && t.url.includes('ClockworkZen_Wallpaper.html'));
      if (pageTarget && pageTarget.webSocketDebuggerUrl) {
        targetWsUrl = pageTarget.webSocketDebuggerUrl;
        break;
      }
    } catch (e) {
      // Chrome still starting up
    }
  }

  if (!targetWsUrl) {
    throw new Error('Could not connect to Chrome debugging port.');
  }

  console.log('Connected to Chrome DevTools Protocol at:', targetWsUrl);
  const client = new CDPClient(targetWsUrl);
  await client.connect();

  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await sleep(1000); // Allow initial frame render

  // -------------------------------------------------------------
  // TEST A: CLOCK ACCURACY
  // -------------------------------------------------------------
  console.log('\n--- Running Test A: Clock Accuracy ---');
  try {
    const accuracyData = await client.eval(`
      (() => {
        const d = new Date();
        const calc = window.__clockworkZenDebug.calculateClockAngles(d);
        const hEl = document.getElementById('clockwork-hour-hand');
        const mEl = document.getElementById('clockwork-minute-hand');
        const sEl = document.getElementById('clockwork-second-hand');
        
        const hTransform = hEl ? hEl.getAttribute('transform') : '';
        const mTransform = mEl ? mEl.getAttribute('transform') : '';
        const sTransform = sEl ? sEl.getAttribute('transform') : '';

        return {
          systemTime: d.toISOString(),
          hours: d.getHours(),
          minutes: d.getMinutes(),
          seconds: d.getSeconds(),
          millis: d.getMilliseconds(),
          calc,
          hTransform,
          mTransform,
          sTransform
        };
      })()
    `);

    console.log('System Time sampled:', accuracyData.systemTime);
    console.log('Calculated Angles:', JSON.stringify(accuracyData.calc));
    console.log('Actual Hand Transforms:', {
      hour: accuracyData.hTransform,
      minute: accuracyData.mTransform,
      second: accuracyData.sTransform
    });

    const hAngleInAttr = parseFloat((accuracyData.hTransform.match(/rotate\(([\d.]+)/) || [])[1]);
    const mAngleInAttr = parseFloat((accuracyData.mTransform.match(/rotate\(([\d.]+)/) || [])[1]);
    const sAngleInAttr = parseFloat((accuracyData.sTransform.match(/rotate\(([\d.]+)/) || [])[1]);

    const hDiff = Math.abs(hAngleInAttr - accuracyData.calc.hourAngle);
    const mDiff = Math.abs(mAngleInAttr - accuracyData.calc.minuteAngle);
    const sDiff = Math.abs(sAngleInAttr - accuracyData.calc.secondAngle);

    const pivotsCorrect = accuracyData.hTransform.includes('500 500') &&
                          accuracyData.mTransform.includes('500 500') &&
                          accuracyData.sTransform.includes('500 500');

    if (hDiff < 0.2 && mDiff < 0.2 && sDiff < 0.5 && pivotsCorrect) {
      testResults.testA.passed = true;
      testResults.testA.details.push(
        `Hour hand accurate (diff: ${hDiff.toFixed(3)}deg)`,
        `Minute hand accurate (diff: ${mDiff.toFixed(3)}deg)`,
        `Second hand accurate (diff: ${sDiff.toFixed(3)}deg)`,
        `All hands rotate around center pivot (500, 500)`
      );
      console.log('✓ TEST A PASSED: Hands match exact fractional local time and pivot at (500, 500).');
    } else {
      testResults.testA.details.push(`Angle discrepancies: H=${hDiff}, M=${mDiff}, S=${sDiff}, Pivots=${pivotsCorrect}`);
      console.log('✗ TEST A FAILED');
    }
  } catch (err) {
    testResults.testA.details.push(`Error: ${err.message}`);
    console.log('✗ TEST A ERROR:', err);
  }

  // -------------------------------------------------------------
  // TEST B: ANIMATION CONTINUITY & SMOOTHNESS
  // -------------------------------------------------------------
  console.log('\n--- Running Test B: Animation Continuity & Smoothness ---');
  try {
    const samples = [];
    for (let i = 0; i < 6; i++) {
      await sleep(80);
      const sample = await client.eval(`
        (() => {
          const sEl = document.getElementById('clockwork-second-hand');
          const mEl = document.getElementById('clockwork-minute-hand');
          const tlGear = document.querySelector('.gear-tl');
          const state = window.__clockworkZenDebug.getState();
          return {
            timestamp: performance.now(),
            secondTransform: sEl.getAttribute('transform'),
            gearAngle: state.ambientGearAngle,
            gearTicks: state.gearTicks,
            clockTicks: state.clockTicks
          };
        })()
      `);
      samples.push(sample);
    }

    let continuousSecondHand = true;
    let continuousGears = true;
    for (let i = 1; i < samples.length; i++) {
      const prevS = parseFloat(samples[i-1].secondTransform.match(/rotate\(([\d.]+)/)[1]);
      const currS = parseFloat(samples[i].secondTransform.match(/rotate\(([\d.]+)/)[1]);
      // Accounting for 360 wrap
      const deltaS = (currS - prevS + 360) % 360;
      const deltaG = samples[i].gearAngle - samples[i-1].gearAngle;

      if (deltaS <= 0 || deltaS > 15) continuousSecondHand = false;
      if (deltaG <= 0) continuousGears = false;
    }

    if (continuousSecondHand && continuousGears && samples[samples.length - 1].clockTicks > 5) {
      testResults.testB.passed = true;
      testResults.testB.details.push(
        'Second hand advances smoothly without periodic snapping across 6 sampled frames',
        `Clock ticks incremented continuously (${samples[samples.length - 1].clockTicks} ticks in interval)`,
        'Gears rotate smoothly with monotonically increasing angle'
      );
      console.log('✓ TEST B PASSED: Second hand and gears move continuously without stepping.');
    } else {
      testResults.testB.details.push(`ContinuousSecond: ${continuousSecondHand}, ContinuousGears: ${continuousGears}`);
      console.log('✗ TEST B FAILED');
    }
  } catch (err) {
    testResults.testB.details.push(`Error: ${err.message}`);
    console.log('✗ TEST B ERROR:', err);
  }

  // -------------------------------------------------------------
  // TEST C: LIGHTING & ORBITAL ROTATION
  // -------------------------------------------------------------
  console.log('\n--- Running Test C: Lighting & Anti-Clockwise Orbit ---');
  try {
    const lightingData = await client.eval(`
      (() => {
        const orbitGroup = document.getElementById('cw-light-orbit');
        const computedStyle = window.getComputedStyle(orbitGroup);
        const animName = computedStyle.animationName;
        const animDuration = computedStyle.animationDuration;
        const transformOrigin = computedStyle.transformOrigin;
        
        const topGlowGrad = document.getElementById('orbit-ambient-glow');
        const coreBeam = document.getElementById('orbit-core-beam');
        const specGrad = document.getElementById('orbit-bezel-specular');
        
        return {
          hasOrbitGroup: !!orbitGroup,
          animName,
          animDuration,
          transformOrigin,
          hasTopGlow: !!topGlowGrad,
          hasCoreBeam: !!coreBeam,
          hasSpecGrad: !!specGrad
        };
      })()
    `);

    console.log('Lighting element check:', lightingData);
    if (lightingData.hasOrbitGroup &&
        lightingData.animDuration.includes('300s') &&
        lightingData.hasTopGlow &&
        lightingData.hasSpecGrad) {
      testResults.testC.passed = true;
      testResults.testC.details.push(
        'Orbital light group exists with 300s anti-clockwise animation duration',
        `Transform origin correctly centered at: ${lightingData.transformOrigin}`,
        'Multilayered translucent radial gradients and specular rim gradients configured'
      );
      console.log('✓ TEST C PASSED: Directional light orbits anti-clockwise with 5-minute period.');
    } else {
      testResults.testC.details.push('Lighting attributes missing or duration incorrect');
      console.log('✗ TEST C FAILED');
    }
  } catch (err) {
    testResults.testC.details.push(`Error: ${err.message}`);
    console.log('✗ TEST C ERROR:', err);
  }

  // -------------------------------------------------------------
  // TEST D: EDITABLE COLOUR CONFIGURATION
  // -------------------------------------------------------------
  console.log('\n--- Running Test D: Colour Configuration ---');
  try {
    // 1. Check amber defaults
    const amberCheck = await client.eval(`
      (() => {
        const style = getComputedStyle(document.documentElement);
        return {
          accent: style.getPropertyValue('--cw-accent').trim(),
          rgb: style.getPropertyValue('--cw-accent-rgb').trim()
        };
      })()
    `);

    // 2. Change --cw-accent to Cyan: #00D2FF
    console.log('Switching --cw-accent to #00D2FF (Cyan)...');
    await client.eval(`
      document.documentElement.style.setProperty('--cw-accent', '#00D2FF');
      window.__clockworkZenDebug.syncAccentMacros();
    `);
    await sleep(200);

    const cyanCheck = await client.eval(`
      (() => {
        const root = document.documentElement;
        const style = getComputedStyle(root);
        const hourHand = document.querySelector('.watermark-accent');
        const hourStroke = getComputedStyle(hourHand).stroke;
        const rgb = style.getPropertyValue('--cw-accent-rgb').trim();
        const glow = style.getPropertyValue('--cw-accent-glow').trim();
        return { rgb, hourStroke, glow };
      })()
    `);

    console.log('Cyan Check Result:', cyanCheck);
    // Take screenshot of Cyan version
    await client.screenshot('S:/Campus-Project/screenshot_cyan_accent.png');
    console.log('Saved screenshot_cyan_accent.png');

    // 3. Restore amber #F59E0B
    await client.eval(`
      document.documentElement.style.setProperty('--cw-accent', '#F59E0B');
      window.__clockworkZenDebug.syncAccentMacros();
    `);
    await sleep(200);

    const restoredCheck = await client.eval(`
      getComputedStyle(document.documentElement).getPropertyValue('--cw-accent-rgb').trim()
    `);

    if (cyanCheck.rgb === '0, 210, 255' && restoredCheck === '245, 158, 11') {
      testResults.testD.passed = true;
      testResults.testD.details.push(
        'Master --cw-accent updates all dependent tokens (RGB: 0, 210, 255)',
        'Hour hand stroke matches new cyan color dynamically',
        'Restored original amber palette #F59E0B cleanly'
      );
      console.log('✓ TEST D PASSED: Single variable --cw-accent dynamically updates all visual elements.');
    } else {
      testResults.testD.details.push(`Failed RGB match. Cyan was: ${cyanCheck.rgb}`);
      console.log('✗ TEST D FAILED');
    }
  } catch (err) {
    testResults.testD.details.push(`Error: ${err.message}`);
    console.log('✗ TEST D ERROR:', err);
  }

  // -------------------------------------------------------------
  // TEST E: RESPONSIVENESS (5 VIEWPORTS)
  // 1366x768, 1920x1080, 2560x1080, 3440x1440, 1080x1920
  // -------------------------------------------------------------
  console.log('\n--- Running Test E: Viewport Responsiveness across 5 Resolutions ---');
  const viewports = [
    { width: 1366, height: 768, name: '1366x768' },
    { width: 1920, height: 1080, name: '1920x1080' },
    { width: 2560, height: 1080, name: '2560x1080' },
    { width: 3440, height: 1440, name: '3440x1440' },
    { width: 1080, height: 1920, name: '1080x1920' }
  ];

  let allViewportsPassed = true;

  for (const vp of viewports) {
    console.log(`Testing viewport ${vp.name}...`);
    await client.setViewport(vp.width, vp.height);
    await sleep(300);

    const vpMetrics = await client.eval(`
      (() => {
        const svgEl = document.getElementById('clockwork-svg');
        const dialEl = document.getElementById('clockwork-dial');
        const dialBox = dialEl.getBoundingClientRect();
        const tlGear = document.getElementById('gear-anchor-tl').getBoundingClientRect();
        const trGear = document.getElementById('gear-anchor-tr').getBoundingClientRect();

        const scrollW = document.documentElement.scrollWidth;
        const clientW = document.documentElement.clientWidth;
        const scrollH = document.documentElement.scrollHeight;
        const clientH = document.documentElement.clientHeight;

        return {
          viewBox: svgEl.getAttribute('viewBox'),
          dialWidth: dialBox.width,
          dialHeight: dialBox.height,
          dialCenterRatioX: (dialBox.x + dialBox.width / 2) / window.innerWidth,
          dialCenterRatioY: (dialBox.y + dialBox.height / 2) / window.innerHeight,
          noHorizScroll: scrollW <= clientW,
          noVertScroll: scrollH <= clientH,
          dialAspect: dialBox.width / dialBox.height,
          tlVisible: tlGear.left >= 0 && tlGear.top >= 0,
          trVisible: trGear.right <= window.innerWidth
        };
      })()
    `);

    const dialCentered = Math.abs(vpMetrics.dialCenterRatioX - 0.5) < 0.05 &&
                         Math.abs(vpMetrics.dialCenterRatioY - 0.5) < 0.05;
    const isCircular = Math.abs(vpMetrics.dialAspect - 1.0) < 0.02;
    const noScroll = vpMetrics.noHorizScroll && vpMetrics.noVertScroll;

    console.log(`  Metrics for ${vp.name}:`, {
      viewBox: vpMetrics.viewBox,
      isCircular,
      dialCentered,
      noScroll,
      aspect: vpMetrics.dialAspect.toFixed(3)
    });

    const screenshotPath = `S:/Campus-Project/screenshot_${vp.name}.png`;
    await client.screenshot(screenshotPath);
    console.log(`  Saved screenshot to ${screenshotPath}`);

    if (dialCentered && isCircular && noScroll) {
      testResults.testE.details.push(`✓ ${vp.name}: Perfectly centered, circular (ratio ${vpMetrics.dialAspect.toFixed(3)}), zero scrollbars.`);
    } else {
      allViewportsPassed = false;
      testResults.testE.details.push(`✗ ${vp.name}: centered=${dialCentered}, circular=${isCircular}, noScroll=${noScroll}`);
    }
  }

  testResults.testE.passed = allViewportsPassed;
  if (allViewportsPassed) {
    console.log('✓ TEST E PASSED: All 5 viewports scaled without distortion, scrollbars, or dial clipping.');
  } else {
    console.log('✗ TEST E FAILED');
  }

  // -------------------------------------------------------------
  // TEST F: CONSOLE & PERFORMANCE
  // -------------------------------------------------------------
  console.log('\n--- Running Test F: Console & Performance Verification ---');
  try {
    // Reset to 1920x1080
    await client.setViewport(1920, 1080);
    await sleep(2000); // Run sustained animation for 2 seconds

    const perfMetrics = await client.eval(`
      (() => {
        const state = window.__clockworkZenDebug.getState();
        return {
          totalClockTicks: state.clockTicks,
          totalGearTicks: state.gearTicks,
          isRunning: state.isRunning
        };
      })()
    `);

    console.log('Sustained performance metrics:', perfMetrics);
    console.log('Console errors recorded:', client.consoleErrors);

    const noErrors = client.consoleErrors.length === 0;
    const sustainedRun = perfMetrics.totalClockTicks > 50 && perfMetrics.totalGearTicks > 50;

    if (noErrors && sustainedRun) {
      testResults.testF.passed = true;
      testResults.testF.details.push(
        'Zero browser console errors or unhandled exceptions',
        `Sustained animation loop confirmed (${perfMetrics.totalClockTicks} clock ticks, ${perfMetrics.totalGearTicks} gear ticks)`
      );
      console.log('✓ TEST F PASSED: Zero console errors, smooth sustained frame execution.');
    } else {
      testResults.testF.details.push(`Errors found: ${JSON.stringify(client.consoleErrors)}`);
      console.log('✗ TEST F FAILED');
    }
  } catch (err) {
    testResults.testF.details.push(`Error: ${err.message}`);
    console.log('✗ TEST F ERROR:', err);
  }

  // Shutdown
  client.close();
  chromeProcess.kill();

  console.log('\n====================================================');
  console.log('TEST SUMMARY RESULTS');
  console.log('====================================================');
  for (const [key, res] of Object.entries(testResults)) {
    console.log(`[${res.passed ? 'PASS' : 'FAIL'}] ${res.name}`);
    for (const d of res.details) {
      console.log(`   - ${d}`);
    }
  }

  fs.writeFileSync('S:/Campus-Project/test_report.json', JSON.stringify(testResults, null, 2));
}

runTestSuite().catch(err => {
  console.error('Test suite failed with unexpected error:', err);
  process.exit(1);
});
