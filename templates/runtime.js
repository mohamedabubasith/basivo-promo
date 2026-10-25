/* basivo-promo runtime: builds every scene from window.__PROMO__ on one master timeline.
   All motion is Web Animations API, paused; window.__seek(t) sets every animation to time t
   so the renderer can capture any frame exactly. Motion rules: docs/MOTION.md. */
(() => {
  "use strict";
  const P = window.__PROMO__;
  const stage = document.getElementById("stage");
  document.body.classList.add(P.layout); // landscape | portrait | square: drives the CSS layouts
  const anims = [];      // every Animation, all paused
  const tickers = [];    // (t) => void, for things WAAPI cannot animate (text, visibility)
  const videos = [];     // { el, start, ready, sync(t) }
  const waits = [];      // promises that must settle before the first frame
  const deferred = [];   // layout-dependent builders, run after media and fonts are ready
  const S = P.speed;     // brand personality: duration multiplier

  // ---------- easing ----------
  const E = {
    out: "cubic-bezier(0.05, 0.7, 0.1, 1)",       // emphasized decelerate: entrances
    in: "cubic-bezier(0.3, 0, 1, 1)",             // accelerate: exits
    inout: "cubic-bezier(0.2, 0, 0, 1)",          // standard: on-screen moves
    seamOut: "cubic-bezier(0.895, 0.03, 0.685, 0.22)", // power4.in: leaving scene, still accelerating at the cut
    seamIn: "cubic-bezier(0.165, 0.84, 0.44, 1)",      // power4.out: entering scene, already moving
    sine: "cubic-bezier(0.37, 0, 0.63, 1)",       // loops and drift
  };
  function spring(stiffness, damping) {
    // Damped spring 0 -> 1 sampled into a CSS linear() easing; returns {easing, seconds}.
    const w0 = Math.sqrt(stiffness), z = damping / (2 * Math.sqrt(stiffness));
    const x = (t) => {
      if (z < 1) { const wd = w0 * Math.sqrt(1 - z * z); return 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + (z * w0 / wd) * Math.sin(wd * t)); }
      return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
    };
    let T = 0.2;
    for (let t = 0; t < 6; t += 0.005) if (Math.abs(x(t) - 1) > 0.002) T = t;
    const pts = [];
    for (let i = 0; i <= 48; i++) pts.push(i === 48 ? 1 : +x((T * i) / 48).toFixed(4));
    return { easing: `linear(${pts.join(", ")})`, seconds: T };
  }
  const SPRING = spring(260, 20);       // standard pop, ~6% overshoot
  const SPRING_SOFT = spring(170, 24);  // gentle settle
  function bezier(x1, y1, x2, y2) {     // for tickers that must follow a curve
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t, sy = (t) => ((ay * t + by) * t + cy) * t;
    return (x) => {
      let lo = 0, hi = 1, t = x;
      for (let i = 0; i < 40; i++) { const v = sx(t); if (Math.abs(v - x) < 1e-6) break; if (v < x) lo = t; else hi = t; t = (lo + hi) / 2; }
      return sy(t);
    };
  }

  // ---------- helpers ----------
  function el(tag, cls, parent, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function anim(target, keyframes, start, dur, easing, opts) {
    const a = target.animate(keyframes, Object.assign({ delay: start * 1000, duration: Math.max(1, dur * 1000), easing, fill: "both" }, opts || {}));
    a.pause();
    a.persist();
    anims.push(a);
    return a;
  }
  // Entrance: from-state -> resting state. Elements use nested wrappers so one property is
  // only ever driven by one animation.
  function enter(target, from, start, dur, easing) {
    const to = {};
    for (const k of Object.keys(from)) to[k] = k === "opacity" ? 1 : k === "filter" ? "blur(0px)" : k === "transform" ? "none" : null;
    return anim(target, [from, to], start, dur, easing || E.out);
  }
  function isVideo(url) { return /\.(mp4|webm|mov|m4v)$/i.test(url); }
  function media(url, parent, start) {
    if (isVideo(url)) {
      const v = el("video", "", parent);
      v.muted = true; v.playsInline = true; v.preload = "auto"; v.src = url;
      const rec = { el: v, start };
      rec.ready = new Promise((res, rej) => {
        if (v.readyState >= 2) res();
        v.addEventListener("loadeddata", () => res(), { once: true });
        v.addEventListener("error", () => rej(new Error("cannot load video " + decodeURI(url.split("/").pop()))), { once: true });
      });
      rec.sync = (t) => {
        const d = v.duration || 0;
        const local = Math.max(0, Math.min(t - rec.start, Math.max(0, d - 1 / P.fps)));
        if (Math.abs(v.currentTime - local) < 0.0005) return null;
        return new Promise((res) => {
          const done = () => { clearTimeout(timer); res(); };
          const timer = setTimeout(done, 3000);
          v.addEventListener("seeked", done, { once: true });
          v.currentTime = local;
        });
      };
      videos.push(rec);
      waits.push(rec.ready);
      return v;
    }
    const img = el("img", "", parent);
    img.decoding = "sync";
    img.src = url;
    waits.push(img.decode().catch(() => { throw new Error("cannot load image " + decodeURI(url.split("/").pop())); }));
    return img;
  }
  function naturalSize(m) { return m.tagName === "VIDEO" ? [m.videoWidth, m.videoHeight] : [m.naturalWidth, m.naturalHeight]; }
  function offsetIn(node, ancestor) { // layout position, ignoring transforms
    let x = 0, y = 0, n = node;
    while (n && n !== ancestor) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent; }
    return [x, y];
  }

  // Split text into word spans; *words* in asterisks get the brand highlight. Waterfall in.
  function words(parent, cls, text, start, opts) {
    const o = Object.assign({ per: "word", dur: 0.7, rise: "0.55em", blur: 10 }, opts || {});
    const box = el("div", cls, parent);
    if (text.length > 30 && cls.includes("display")) box.classList.add("long");
    const units = [];
    text.split(/(\*[^*]+\*)/).forEach((part) => {
      if (!part) return;
      const hl = part.startsWith("*") && part.endsWith("*");
      const body = hl ? part.slice(1, -1) : part;
      const tokens = o.per === "char" ? [...body] : body.split(/(\s+)/);
      tokens.forEach((tok) => {
        if (!tok) return;
        if (/^\s+$/.test(tok)) { box.appendChild(document.createTextNode(" ")); return; }
        const w = el("span", "w", box);
        const inner = el("span", hl ? "hl" : "", w, tok);
        units.push(inner);
      });
    });
    const n = units.length;
    const stagger = Math.min(o.per === "char" ? 0.03 : 0.05, 0.45 / Math.max(1, n - 1)); // total stagger < 0.5 s
    units.forEach((u, i) => enter(u, { transform: `translateY(${o.rise})`, opacity: 0, filter: `blur(${o.blur}px)` }, start + i * stagger * S, o.dur * S, E.out));
    return box;
  }

  // ---------- backdrop ----------
  (() => {
    const kind = P.look.backdrop;
    const b = el("div", "backdrop " + kind, stage);
    if (kind === "plain") return;
    const a = el("div", "blob a", b), bb = el("div", "blob b", b), c = el("div", "blob c", b);
    el("div", kind === "grid" ? "lines" : "dots", b);
    const loop = { iterations: Infinity, direction: "alternate" };
    anim(a, [{ transform: "translate(0,0) scale(1)" }, { transform: "translate(12cqw,8cqh) scale(1.15)" }], 0, 11, E.sine, loop);
    anim(bb, [{ transform: "translate(0,0) scale(1.1)" }, { transform: "translate(-10cqw,-9cqh) scale(0.95)" }], 0, 13, E.sine, loop);
    anim(c, [{ transform: "translate(0,0)" }, { transform: "translate(-14cqw,6cqh)" }], 0, 17, E.sine, loop);
  })();

  // ---------- scene shells and seams ----------
  const shells = P.timeline.map((tm, i) => {
    const sec = el("section", "scene", stage);
    const seamIn = el("div", "seam-in", sec);
    const seamOut = el("div", "seam-out", seamIn);
    const drift = el("div", "drift", seamOut);
    const content = el("div", "content", drift);
    const end = tm.start + tm.dur;
    tickers.push((t) => { sec.style.visibility = t >= tm.start && t < end ? "visible" : "hidden"; });
    // Sustained motion: the whole scene keeps a slow push so no cut lands on a still frame.
    anim(drift, [{ transform: "scale(1)" }, { transform: "scale(1.035)" }], tm.start, tm.dur, E.sine);
    return { sec, seamIn, seamOut, content, tm, i };
  });
  // Vector law: the outgoing scene leaves on the same axis and direction the incoming one
  // arrives, with mirrored power4 eases so speed matches at the cut. Never a plain crossfade.
  shells.forEach((sh, i) => {
    if (i === 0 || sh.tm.transition === "cut") return;
    const prev = shells[i - 1], T = sh.tm.start, D = sh.tm.tr;
    let outK, inK;
    if (sh.tm.transition === "push-up") {
      outK = [{ transform: "translateY(0)", opacity: 1, filter: "blur(0px)" }, { opacity: 1, offset: 0.55 }, { transform: "translateY(-35%)", opacity: 0, filter: "blur(6px)" }];
      inK = [{ transform: "translateY(35%)", opacity: 0, filter: "blur(6px)" }, { opacity: 1, offset: 0.45 }, { transform: "translateY(0)", opacity: 1, filter: "blur(0px)" }];
    } else if (sh.tm.transition === "zoom") { // Z forward: both sides grow, pushing deeper
      outK = [{ transform: "scale(1)", opacity: 1, filter: "blur(0px)" }, { opacity: 1, offset: 0.5 }, { transform: "scale(1.6)", opacity: 0, filter: "blur(8px)" }];
      inK = [{ transform: "scale(0.72)", opacity: 0, filter: "blur(8px)" }, { opacity: 1, offset: 0.5 }, { transform: "scale(1)", opacity: 1, filter: "blur(0px)" }];
    } else { // push-left, the house current
      outK = [{ transform: "translateX(0)", opacity: 1, filter: "blur(0px)" }, { opacity: 1, offset: 0.55 }, { transform: "translateX(-35%)", opacity: 0, filter: "blur(6px)" }];
      inK = [{ transform: "translateX(35%)", opacity: 0, filter: "blur(6px)" }, { opacity: 1, offset: 0.45 }, { transform: "translateX(0)", opacity: 1, filter: "blur(0px)" }];
    }
    anim(prev.seamOut, outK, T, D, E.seamOut);
    anim(sh.seamIn, inK, T, D, E.seamIn);
  });

  // ---------- device frame ----------
  // Builds a frame (browser, phone, laptop, none) holding media; sized after media loads.
  function device(parent, url, kind, start, opts) {
    const o = Object.assign({ pan: "push", bar: true }, opts || {});
    const box = el("div", "device-box", parent);
    const fw = el("div", "frame-wrap", box);
    const frame = el("div", "frame " + (kind === "phone" ? "phone" : kind === "none" ? "none" : ""), fw);
    let bar = null;
    if (kind === "browser" || kind === "laptop") {
      bar = el("div", "bar", frame);
      el("i", "", bar); el("i", "", bar); el("i", "", bar);
      el("b", "", bar, P.host || P.product);
    }
    if (kind === "phone") el("div", "island", frame);
    const screen = el("div", "screen", frame);
    const pan = el("div", "pan", screen);
    const m = media(url, pan, start);
    const base = kind === "laptop" ? el("div", "laptop-base", fw) : null;
    const api = { box, fw, frame, screen, pan, media: m, rect: null };
    deferred.push(() => {
      const [nw, nh] = naturalSize(m);
      const bw = box.clientWidth, bh = box.clientHeight;
      const barH = bar ? Math.max(28, Math.round(bw * 0.028)) : 0;
      // Viewport aspect: phones keep the phone shape; tall full-page shots show a 16:10 window and scroll.
      let aspect = nw / nh;
      if (o.pan === "down" && aspect < 1.2 && kind !== "phone") aspect = 1.6;
      if (kind === "phone") aspect = Math.min(aspect, 0.5);
      aspect = Math.min(Math.max(aspect, 0.42), 2.4);
      const baseH = base ? bh * 0.045 : 0;
      let w = bw, h = w / aspect + barH;
      if (h > bh - baseH) { h = bh - baseH; w = (h - barH) * aspect; }
      const x = (bw - w) / 2, y = (bh - baseH - h) / 2;
      Object.assign(fw.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
      if (bar) bar.style.height = barH + "px";
      screen.style.top = barH + "px";
      if (base) base.style.top = h + "px";
      if (kind === "phone") { screen.style.inset = `${w * 0.035}px`; }
      const sw = screen.clientWidth || w, sh = screen.clientHeight || h - barH;
      const mh = (sw * nh) / nw; // media height when fitted to screen width
      if (mh < sh) { pan.style.top = (sh - mh) / 2 + "px"; }
      api.rect = { x, y, w, h, barH, sw, sh, mh };
      // Camera motion inside the screen.
      if (o.pan === "down" && mh > sh * 1.05) {
        anim(pan, [{ transform: "translateY(0)" }, { transform: `translateY(${-(mh - sh)}px)` }], o.panStart, Math.max(0.8, o.panEnd - o.panStart), E.inout);
      } else if (o.pan === "push") {
        anim(pan, [{ transform: "scale(1)" }, { transform: "scale(1.08)" }], o.panStart, Math.max(0.8, o.panEnd - o.panStart), E.sine);
      }
    });
    // Entrance: rise from below with a slight tilt, like a product placed on a table.
    enter(fw, { transform: "translateY(45cqh)", opacity: 0 }, start, 0.9 * S, E.out);
    enter(frame, { transform: "rotateX(16deg) scale(0.94)" }, start, 1.1 * S, E.out);
    return api;
  }

  // ---------- scenes ----------
  // Logo, or a monogram when there is none. Wide logos are lockups (mark + name): they get a
  // wide box and onLockup() lets the scene drop its own wordmark so the name is not shown twice.
  const brandMark = (parent, cls, onLockup) => {
    const mk = el("div", cls, parent);
    if (P.brand.logo) {
      const img = media(P.brand.logo, mk, 0);
      deferred.unshift(() => {
        const [w, h] = naturalSize(img);
        if (w && h && w / h > 2.2) { mk.classList.add("lockup"); if (onLockup) onLockup(); }
      });
    } else el("div", "monogram", mk, (P.product.trim()[0] || "•").toUpperCase());
    return mk;
  };

  const SCENES = {
    logo(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      const name = s.text || P.product;
      let wm = null;
      const mk = brandMark(sh.content, "mark", () => { if (!s.text && wm) wm.style.display = "none"; });
      anim(mk, [{ transform: "scale(0.5)", opacity: 0, filter: "blur(16px)" }, { transform: "scale(1)", opacity: 1, filter: "blur(0px)" }], t0 + 0.1, SPRING.seconds, SPRING.easing);
      wm = words(sh.content, "wordmark", name, t0 + 0.45 * S, { per: "char", dur: 0.6 });
      const shine = el("div", "shine", wm, name.replace(/\*/g, ""));
      anim(shine, [{ backgroundPosition: "100% 0" }, { backgroundPosition: "0% 0" }], t0 + 1.1 * S, 1.0 * S, E.inout);
      if (s.sub) words(sh.content, "sub", s.sub, t0 + 0.9 * S);
    },
    headline(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      if (s.eyebrow) words(sh.content, "eyebrow", s.eyebrow, t0, { rise: "0.8em" });
      words(sh.content, "display", s.text, t0 + (s.eyebrow ? 0.15 : 0) * S);
      if (s.sub) words(sh.content, "sub", s.sub, t0 + 0.45 * S);
    },
    device(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      const hasCopy = s.title || s.caption;
      if (hasCopy) sh.content.classList.add("split-x");
      if (hasCopy) {
        const copy = el("div", "copy", sh.content);
        if (s.title) words(copy, "title", s.title, t0);
        if (s.caption) words(copy, "sub", s.caption, t0 + 0.3 * S);
      }
      device(sh.content, s.media, s.frame || "browser", t0 + 0.1 * S, { pan: s.pan || "push", panStart: t0 + 0.9 * S, panEnd: sh.tm.start + sh.tm.dur - 0.3 });
    },
    click(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      if (s.title) words(sh.content, "title", s.title, t0);
      const camera = el("div", "camera", null);
      camera.style.perspective = "140cqmin"; // keeps the frame's tilted entrance 3D inside the zoom
      const dev = device(sh.content, s.media, s.frame || "browser", t0 + 0.1 * S, { pan: "none" });
      // Camera wrapper sits between frame-wrap and frame so the zoom keeps the entrance intact.
      dev.fw.appendChild(camera);
      camera.appendChild(dev.frame);
      if (dev.fw.querySelector(".laptop-base")) dev.fw.appendChild(dev.fw.querySelector(".laptop-base"));
      const cursor = el("div", "cursor", sh.content);
      const [body, edge] = P.look.cursor === "light" ? ["#fff", "#111"] : ["#111", "#fff"];
      cursor.innerHTML = `<svg viewBox="0 0 32 32"><path d="M6 3 L6 26 L12 20.5 L16 29.2 L20.2 27.4 L16.2 18.9 L24 18.9 Z" fill="${body}" stroke="${edge}" stroke-width="1.7" stroke-linejoin="round"/></svg>`;
      const ripple = el("div", "ripple", sh.content);
      const callout = s.label ? el("div", "callout", sh.content, s.label) : null;
      const tClick = sh.tm.click_at; // shared with the click sound in the audio mix
      deferred.push(() => {
        const r = dev.rect;
        const [bx, by] = offsetIn(dev.box, sh.content);
        // Point in content coordinates (media fitted to screen width, top-aligned or centred).
        const padTop = r.mh < r.sh ? (r.sh - r.mh) / 2 : 0;
        const inset = dev.frame.classList.contains("phone") ? r.w * 0.035 : 0;
        const px = bx + r.x + inset + s.point[0] * r.sw;
        const py = by + r.y + r.barH + inset + padTop + s.point[1] * Math.min(r.mh, r.sh);
        const cw = cursor.offsetWidth, tipX = cw * (6 / 32), tipY = cw * (3 / 32);
        const H = sh.content.clientHeight, W = sh.content.clientWidth;
        const atX = px - tipX, atY = py - tipY;
        cursor.style.left = "0px"; cursor.style.top = "0px";
        // Enters from below (never faded in), glides to the target, clicks, then carries the eye out.
        anim(cursor, [
          { transform: `translate(${atX + W * 0.12}px, ${H + cw}px)` },
          { transform: `translate(${atX}px, ${atY}px)` },
        ], t0 + 0.5 * S, 1.0 * S, E.out);
        const exitAt = sh.tm.start + sh.tm.dur - 0.85;
        const press = el("div", "", null);
        cursor.parentNode.insertBefore(press, cursor); press.appendChild(cursor);
        press.style.position = "absolute"; press.style.inset = "0"; press.style.zIndex = 5; press.style.pointerEvents = "none";
        anim(press, [{ transform: "translate(0,0)" }, { transform: `translate(${W * 0.25}px, ${H * 0.6}px)` }], exitAt, 0.75, E.in);
        const squash = el("div", "", null);
        cursor.parentNode.insertBefore(squash, cursor); squash.appendChild(cursor);
        squash.style.position = "absolute"; squash.style.inset = "0";
        squash.style.transformOrigin = `${atX + tipX}px ${atY + tipY}px`;
        anim(squash, [{ transform: "scale(1)" }, { transform: "scale(0.8)", offset: 0.25 }, { transform: "scale(1)" }], tClick, 0.32, E.inout);
        ripple.style.left = px + "px"; ripple.style.top = py + "px";
        anim(ripple, [{ transform: "scale(0.2)", opacity: 0.95 }, { transform: "scale(2.8)", opacity: 0 }], tClick, 0.65, E.out, { fill: "forwards" });
        // Zoom toward the click; the origin is the click point so cursor and ripple stay on it.
        camera.style.transformOrigin = `${px - bx - r.x}px ${py - by - r.y}px`;
        anim(camera, [{ transform: "scale(1)" }, { transform: "scale(1.7)" }], tClick + 0.12, 1.0 * S, E.inout);
        if (callout) {
          const left = s.point[0] > 0.62;
          callout.style.top = Math.max(0, py - callout.offsetHeight - cw * 0.7) + "px";
          if (left) callout.style.right = W - px + cw * 0.4 + "px"; else callout.style.left = px + cw * 0.6 + "px";
          callout.style.transformOrigin = left ? "100% 100%" : "0% 100%";
          anim(callout, [{ transform: "scale(0.6)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], tClick + 0.5 * S, SPRING.seconds, SPRING.easing);
        }
      });
    },
    features(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      if (s.title) words(sh.content, "title", s.title, t0);
      const n = s.items.length, L = P.layout;
      const cols = L === "landscape" ? (n <= 4 ? n : 3) : L === "square" ? (n === 3 ? 1 : 2) : (n <= 4 ? 1 : 2);
      const grid = el("div", "grid", sh.content);
      grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
      const mid = (n - 1) / 2;
      const order = s.items.map((_, i) => i).sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid) || a - b); // centre-out
      const stagger = Math.min(0.08, 0.45 / Math.max(1, n - 1));
      s.items.forEach((it, i) => {
        const card = el("div", "card", grid);
        const ic = it.icon ? el("div", "ic", card, it.icon) : null;
        el("h3", "", card, it.title);
        if (it.text) el("p", "", card, it.text);
        const at = t0 + (0.25 + order.indexOf(i) * stagger) * S;
        enter(card, { transform: "translateY(5cqmin) scale(0.96)", opacity: 0, filter: "blur(6px)" }, at, 0.65 * S, E.out);
        if (ic) anim(ic, [{ transform: "scale(0.4)" }, { transform: "scale(1)" }], at + 0.15 * S, SPRING.seconds, SPRING.easing);
      });
    },
    split(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      if (s.title) words(sh.content, "title", s.title, t0);
      const box = el("div", "device-box", sh.content);
      const cmp = el("div", "compare", box);
      cmp.style.position = "absolute";
      const before = media(s.before, cmp, t0);
      const afterWrap = el("div", "", cmp);
      afterWrap.style.cssText = "position:absolute;inset:0;z-index:2";
      media(s.after, afterWrap, t0);
      const div = el("div", "divider", cmp);
      el("div", "knob", div);
      const labels = s.labels || ["Before", "After"];
      const c1 = el("div", "chip", cmp, labels[0]), c2 = el("div", "chip", cmp, labels[1]);
      c1.style.left = "2cqmin"; c2.style.right = "2cqmin";
      const vertical = P.layout === "portrait";
      if (vertical) { c2.style.top = "auto"; c2.style.bottom = "2cqmin"; }
      deferred.push(() => {
        const [nw, nh] = naturalSize(before);
        const bw = box.clientWidth, bh = box.clientHeight;
        let w = bw, h = (bw * nh) / nw;
        if (h > bh) { h = bh; w = (bh * nw) / nh; }
        Object.assign(cmp.style, { width: w + "px", height: h + "px", left: (bw - w) / 2 + "px", top: (bh - h) / 2 + "px" });
      });
      enter(cmp, { transform: "translateY(30cqh)", opacity: 0 }, t0, 0.9 * S, E.out);
      const w0 = t0 + 0.9 * S, wd = 1.2 * S;
      if (vertical) {
        anim(afterWrap, [{ clipPath: "inset(100% 0 0 0)" }, { clipPath: "inset(50% 0 0 0)" }], w0, wd, E.inout);
        anim(div, [{ top: "100%" }, { top: "50%" }], w0, wd, E.inout);
      } else {
        anim(afterWrap, [{ clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 50%)" }], w0, wd, E.inout);
        anim(div, [{ left: "100%" }, { left: "50%" }], w0, wd, E.inout);
      }
      enter(c1, { opacity: 0, transform: "translateY(-1cqmin)" }, t0 + 0.6 * S, 0.4 * S);
      enter(c2, { opacity: 0, transform: "translateY(-1cqmin)" }, w0 + wd * 0.7, 0.4 * S);
    },
    stat(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      const num = el("div", "stat-num", sh.content);
      enter(num, { transform: "scale(0.88)", opacity: 0, filter: "blur(12px)" }, t0, 0.7 * S, E.out);
      const d = s.decimals || 0, from = s.from || 0, to = s.value;
      const fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
      const ease = bezier(0.16, 1, 0.3, 1);
      const c0 = t0 + 0.15 * S, cd = 1.5 * S;
      tickers.push((t) => {
        const p = Math.max(0, Math.min(1, (t - c0) / cd));
        num.textContent = (s.prefix || "") + fmt.format(from + (to - from) * ease(p)) + (s.suffix || "");
      });
      const bar = el("div", "stat-bar", sh.content);
      anim(bar, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], t0 + 0.5 * S, 0.9 * S, E.out);
      words(sh.content, "sub", s.label, t0 + 0.55 * S);
    },
    cta(s, sh) {
      const t0 = sh.tm.start + sh.tm.tr * 0.5;
      const mk = brandMark(sh.content, "mark cta-mark");
      anim(mk, [{ transform: "scale(0.6)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], t0, SPRING_SOFT.seconds, SPRING_SOFT.easing);
      words(sh.content, "display", s.text, t0 + 0.15 * S);
      if (s.sub) words(sh.content, "sub", s.sub, t0 + 0.45 * S);
      if (s.button) {
        const pop = el("div", "", sh.content);
        const btn = el("div", "button", pop, s.button);
        anim(pop, [{ transform: "scale(0.5)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], t0 + 0.75 * S, SPRING.seconds, SPRING.easing);
        anim(btn, [{ transform: "scale(1)" }, { transform: "scale(1.045)" }], t0 + 0.75 * S + SPRING.seconds, 0.9, E.sine, { iterations: Infinity, direction: "alternate" });
      }
      if (s.url) enter(el("div", "url", sh.content, s.url), { opacity: 0, transform: "translateY(1.5cqmin)" }, t0 + 1.0 * S, 0.6 * S);
    },
  };

  P.scenes.forEach((s, i) => SCENES[s.type](s, shells[i]));

  // ---------- captions ----------
  if (P.captions && P.captions.length) {
    const box = el("div", "captions", stage);
    const span = el("span", "", box);
    box.style.opacity = 0;
    tickers.push((t) => {
      const c = P.captions.find((q) => t >= q.start - 0.08 && t < q.end + 0.12);
      if (!c) { box.style.opacity = 0; return; }
      if (span.textContent !== c.text) span.textContent = c.text;
      box.style.opacity = Math.max(0, Math.min(1, (t - (c.start - 0.08)) / 0.12, (c.end + 0.12 - t) / 0.12));
    });
  }

  // ---------- driver ----------
  window.__seek = async (t) => {
    const ms = t * 1000;
    for (const a of anims) a.currentTime = ms;
    for (const f of tickers) f(t);
    const pending = videos.map((v) => v.sync(t)).filter(Boolean);
    if (pending.length) await Promise.all(pending);
  };
  window.__ready = (async () => {
    await document.fonts.ready;
    await Promise.all(waits);
    deferred.forEach((f) => f());
    await window.__seek(0);
    return { animations: anims.length, videos: videos.length };
  })();
})();
