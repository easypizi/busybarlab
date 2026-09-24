(function () {
  var SPEECH_CPS = { cyr: 14, lat: 16 };
  var FPS = 12;
  var FRAME = 1000 / FPS;

  function mouthFor(ch) {
    if (!ch || ch === " ") return "mouth_shut";
    var c = ch.toLowerCase();
    if ("aая".indexOf(c) >= 0) return "mouth_a";
    if ("oоuуюё".indexOf(c) >= 0) return "mouth_o";
    if ("eеиыэi".indexOf(c) >= 0) return "mouth_e";
    if ("mмbбpп".indexOf(c) >= 0) return "mouth_m";
    return "mouth_con";
  }

  function delayFor(ch) {
    var cyr = /[а-яё]/i.test(ch);
    var base = 1000 / (cyr ? SPEECH_CPS.cyr : SPEECH_CPS.lat);
    if (ch === "," || ch === ";") return base + 250;
    if (ch === "." || ch === "!" || ch === "?" || ch === "…") return base + 450;
    return base;
  }

  function createStage(canvas, dialog, who) {
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    var cast = window.CAST;
    var layers = cast[who];
    var order = cast.order[who];
    var pal = cast.palette;
    var scale = cast.scale;
    var mode = "idle";
    var since = 0;
    var blinkAt = 800;
    var blinkFor = 0;
    var doubleBlink = false;
    var typed = "";
    var full = "";
    var typeAt = 0;
    var mouth = "mouth_shut";
    var action = "";
    var actionUntil = 0;
    var linesShown = 3;
    var holdUntil = 0;
    var last = 0;
    var acc = 0;
    var nod = 0;

    function setDialog(text, kind) {
      dialog.className = kind || "";
      dialog.textContent = text;
      dialog.scrollTop = dialog.scrollHeight;
    }

    function scheduleBlink(now) {
      blinkAt = now + 2000 + Math.random() * 4000;
      doubleBlink = Math.random() < 0.25;
    }

    function blit(name, ox, oy) {
      var pixels = layers[name];
      if (!pixels) return;
      var i;
      for (i = 0; i < pixels.length; i += 3) {
        ctx.fillStyle = pal[pixels[i + 2]];
        ctx.fillRect((pixels[i] + ox) * scale, (pixels[i + 1] + oy) * scale, scale, scale);
      }
    }

    function draw(now) {
      var breath = now % 3800 > 1900 ? -1 : 0;
      var bobNames = {
        head: 1,
        hair: 1,
        mustache: 1,
        eyes: 1,
        eyes_shut: 1,
        brows: 1,
        mouth_shut: 1,
        mouth_a: 1,
        mouth_o: 1,
        mouth_e: 1,
        mouth_m: 1,
        mouth_con: 1,
        bow: 1,
        hat: 1,
        pencil: 1,
      };
      var lean = mode === "listen" ? 1 : 0;
      var browLift = mode === "listen" && who === "tito" ? -1 : 0;
      var glasses = 0;
      if (mode === "think" && who === "tito") glasses = 3;
      var hatShift = 0;
      if (mode === "think" && who === "paco") hatShift = -2;
      var showBite = mode === "think" && who === "paco";
      var showHand = false;
      if (who === "tito" && mode === "idle" && now % 7000 < 800) showHand = true;
      if (who === "tito" && mode === "speak" && /[,.]/.test(typed.slice(-1))) showHand = true;
      var page = mode === "think" && who === "tito" && Math.floor(now / 180) % 2 === 0;
      if (mode === "listen") nod = Math.floor(now / 700) % 2;
      else nod = 0;
      var blink = blinkFor > 0;

      ctx.fillStyle = "#111111";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      var n;
      for (n = 0; n < order.length; n += 1) {
        var name = order[n];
        if (name === "mouth") name = mouth;
        if (name === "eyes" && blink) name = "eyes_shut";
        if (name === "hand" && !showHand) continue;
        if (name === "mark" && now > actionUntil) continue;
        if (name === "line1" || name === "line2" || name === "line3") {
          var need = name === "line1" ? 1 : name === "line2" ? 2 : 3;
          if (mode === "listen" && linesShown < need) continue;
        }
        if (name === "pencil" && showBite) name = "pencil_bite";
        var ox = 0;
        var oy = 0;
        if (bobNames[name]) {
          oy += breath + lean + nod;
        }
        if (name === "brows") oy += browLift;
        if (name === "eyes" || name === "eyes_shut") oy += glasses;
        if (name === "hat") {
          oy += hatShift;
          ox += hatShift ? 2 : 0;
        }
        if (name === "bow" && showHand) ox += now % 400 < 200 ? -1 : 1;
        if (name === "prop" && who === "tito" && mode === "idle" && now % 9000 < 500) oy -= 1;
        if (name === "prop" && page) ox += 1;
        if (name === "pencil" && mode === "idle" && who === "paco") {
          ox += Math.floor(now / 200) % 3 - 1;
        }
        blit(name, ox, oy);
      }
      if (mode === "think" && who === "paco") {
        ctx.fillStyle = "#fe5000";
        var dots = (Math.floor(now / 200) % 3) + 1;
        var d;
        for (d = 0; d < dots; d += 1) {
          ctx.fillRect((40 + d * 4) * scale, 6 * scale, scale, scale);
        }
      }
    }

    function frame(now) {
      if (!last) last = now;
      acc += now - last;
      last = now;
      if (acc >= FRAME) {
        acc = 0;
        if (blinkFor > 0) blinkFor -= 1;
        else if (now >= blinkAt) {
          blinkFor = 2;
          blinkAt = now + (doubleBlink ? 180 : 0);
          if (!doubleBlink) scheduleBlink(now);
          else doubleBlink = false;
        }
        if (mode === "speak" && typed.length < full.length && now >= typeAt) {
          typed += full.charAt(typed.length);
          mouth = mouthFor(typed.charAt(typed.length - 1));
          typeAt = now + delayFor(typed.charAt(typed.length - 1));
          setDialog(typed, "speak");
          if (who === "paco" && /[.!?]/.test(typed.slice(-1))) actionUntil = now + 400;
          if (typed.length === full.length) holdUntil = now + 4000;
        } else if (mode === "speak" && holdUntil && now >= holdUntil) {
          holdUntil = 0;
          setMode("idle");
        }
        if (mode === "listen" && who === "paco") {
          linesShown = Math.min(3, Math.floor((now - since) / 700));
        }
        draw(now);
      }
      requestAnimationFrame(frame);
    }

    function setMode(next) {
      mode = next;
      since = performance.now();
      if (next !== "speak") mouth = "mouth_shut";
      if (next === "think") setDialog("...", "think");
      if (next === "idle") setDialog("", "");
      if (next === "listen") {
        linesShown = 0;
        holdUntil = 0;
        setDialog("", "user");
      }
    }

    requestAnimationFrame(frame);
    scheduleBlink(performance.now());

    return {
      setMode: setMode,
      heard: function (text) {
        setDialog(text, "user");
      },
      speak: function (text, nextAction) {
        full = text || "";
        typed = "";
        holdUntil = 0;
        typeAt = performance.now();
        action = nextAction || "";
        if (action) actionUntil = performance.now() + 2000;
        setMode("speak");
        mouth = "mouth_shut";
      },
      fail: function (text) {
        full = "";
        typed = "";
        setMode("idle");
        setDialog(text || "", "speak");
      },
      scroll: function (delta) {
        dialog.scrollTop += delta;
      },
    };
  }

  window.createStage = createStage;
})();
