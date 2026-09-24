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

  function createStage(canvas, dialog, who, options) {
    options = options || {};
    var clock = options.clock || function () { return performance.now(); };
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    var cast = window.CAST;
    var layers = cast[who];
    var order = cast.order[who];
    var attach = cast.attach[who];
    var pal = cast.palette;
    var scale = cast.scale;
    var mode = "idle";
    var modeAt = clock();
    var typed = "";
    var full = "";
    var typeAt = 0;
    var mouth = "mouth_shut";
    var mouthNext = "mouth_shut";
    var mouthBlend = 0;
    var action = "";
    var actionUntil = 0;
    var markStart = 0;
    var markUntil = 0;
    var nodUntil = 0;
    var holdUntil = 0;
    var pinned = true;
    var blinkLock = "";
    var sprites = {};
    var last = clock();

    function setDialog(text, kind) {
      dialog.className = kind || "";
      dialog.textContent = text;
      if (pinned) dialog.scrollTop = dialog.scrollHeight;
    }

    function bake(name) {
      if (sprites[name]) return sprites[name];
      var pixels = layers[name];
      if (!pixels) return null;
      var sheet = document.createElement("canvas");
      sheet.width = cast.grid * scale;
      sheet.height = sheet.width;
      var pen = sheet.getContext("2d");
      pen.imageSmoothingEnabled = false;
      var i;
      for (i = 0; i < pixels.length; i += 3) {
        pen.fillStyle = pal[pixels[i + 2]];
        pen.fillRect(pixels[i] * scale, pixels[i + 1] * scale, scale, scale);
      }
      sprites[name] = sheet;
      return sheet;
    }

    function blit(name, ox, oy) {
      var sheet = bake(name);
      if (!sheet) return;
      ctx.drawImage(sheet, ox * scale, oy * scale);
    }

    function blinkShape(now) {
      if (blinkLock) return blinkLock;
      var period = 3000;
      var into = (now + 2200) % period;
      if (into < FRAME) return "eyes_half";
      if (into < 2 * FRAME) return "eyes_shut";
      if (into < 3 * FRAME) return "eyes_half";
      if (Math.floor(now / period) % 4 === 0) {
        var gap = 3 * FRAME + 180;
        if (into >= gap && into < gap + FRAME) return "eyes_half";
        if (into >= gap + FRAME && into < gap + 2 * FRAME) return "eyes_shut";
        if (into >= gap + 2 * FRAME && into < gap + 3 * FRAME) return "eyes_half";
      }
      return "";
    }

    function gazeShape(now) {
      var slot = Math.floor(now / 5000) % 6;
      if (slot === 1) return "eyes_side_l";
      if (slot === 2) return "eyes_side_r";
      return "eyes_open";
    }

    function poseAt(now) {
      var framesIn = Math.max(0, Math.floor((now - modeAt) / FRAME));
      var breath = Math.floor(now / 3800) % 2 === 1 ? -1 : 0;
      var lean = mode === "listen" && framesIn >= 1 ? 1 : 0;
      var nod = 0;
      if (mode === "listen" && framesIn >= 2) nod = Math.floor(now / 700) % 2;
      if (mode === "speak" && who === "paco" && now < nodUntil) nod = 1;
      var headOy = breath + lean + nod;
      var blinked = blinkShape(now);
      var eyes = blinked || (mode === "think" && framesIn >= 1 ? "eyes_up" : gazeShape(now));
      var brows = "brows";
      if (mode === "listen" && framesIn >= 1) brows = "brows_up";
      if (mode === "think" && who === "paco" && framesIn >= 1) brows = "brows_knit";
      var glasses = "glasses";
      if (mode === "think" && who === "tito" && framesIn >= 1) glasses = "glasses_low";
      var mouthName = mode === "speak" ? mouth : "mouth_shut";
      var vowel = mouthName === "mouth_a" || mouthName === "mouth_o";
      if (mouthName === "mouth_mid" && (mouthNext === "mouth_a" || mouthNext === "mouth_o")) vowel = true;
      var shown = ["body", "head", "hair", vowel ? "mustache_open" : "mustache", eyes, glasses, brows, mouthName];
      var extra = {};
      if (who === "tito") {
        var page = "cal_0";
        if (action && now < actionUntil) page = "cal_lit";
        else if (mode === "think") page = "cal_" + (Math.floor(Math.max(0, now - modeAt) / 600) % 3);
        shown.push(page, "bow");
        if (mode === "idle" && now % 8000 < 3 * FRAME) shown.push("hand_bow");
        var last = typed.slice(-1);
        if (mode === "speak" && ",.!?".indexOf(last) >= 0) shown.push("hand_tick");
        if (mode === "listen" && framesIn >= 1) {
          shown.push("glint");
          extra.glint = { ox: (Math.floor(now / 160) % 3) * 3, oy: 0 };
        }
      } else {
        shown.push("notebook");
        if (mode === "think" && framesIn >= 1) {
          shown.push("hat_back", "pencil_bite");
        } else {
          shown.push("hat_crown", "hat_band", "hat_brim");
          if (mode === "listen") {
            shown.push("pencil_write_" + (Math.floor(now / 180) % 3));
            var lines = Math.min(3, Math.floor(Math.max(0, now - modeAt) / 700));
            if (lines >= 1) shown.push("line1");
            if (lines >= 2) shown.push("line2");
            if (lines >= 3) shown.push("line3");
          } else if (mode === "idle" && now % 9000 < 2 * FRAME) shown.push("pencil_touch");
          else shown.push("pencil_ear");
        }
        if (now < markUntil) {
          var age = now - markStart;
          var step = age < 140 ? 0 : age < 280 ? 1 : 2;
          shown.push("mark_" + step);
        }
      }
      var dots = 0;
      if (who === "paco" && mode === "think") {
        dots = framesIn < 2 ? framesIn + 1 : (Math.floor(now / 200) % 3) + 1;
      }
      return { layers: shown, headOy: headOy, extra: extra, dots: dots };
    }

    function draw(now) {
      var pose = poseAt(now);
      var show = {};
      var i;
      for (i = 0; i < pose.layers.length; i += 1) show[pose.layers[i]] = 1;
      ctx.fillStyle = "#111111";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      var n;
      for (n = 0; n < order.length; n += 1) {
        var name = order[n];
        if (!show[name]) continue;
        var ox = 0;
        var oy = attach[name] === "head" ? pose.headOy : 0;
        var bump = pose.extra[name];
        if (bump) {
          ox += bump.ox || 0;
          oy += bump.oy || 0;
        }
        blit(name, ox, oy);
      }
      if (pose.dots) {
        ctx.fillStyle = "#fe5000";
        var d;
        for (d = 0; d < pose.dots; d += 1) {
          ctx.fillRect((72 + d * 5) * scale, (40 + pose.headOy) * scale, scale, scale);
        }
      }
    }

    function tick(now) {
      if (mode === "speak" && mouthBlend > 0) {
        mouthBlend -= 1;
        if (mouthBlend === 0) mouth = mouthNext;
      }
      if (mode === "speak" && typed.length < full.length && now >= typeAt && mouthBlend === 0) {
        var ch = full.charAt(typed.length);
        typed += ch;
        var next = mouthFor(ch);
        if (next !== mouth) {
          mouthNext = next;
          mouth = "mouth_mid";
          mouthBlend = 1;
          typeAt = now + FRAME + delayFor(ch);
        } else {
          mouth = next;
          typeAt = now + delayFor(ch);
        }
        setDialog(typed, "speak");
        if (who === "paco" && /[.!?]/.test(ch)) {
          nodUntil = now + 4 * FRAME;
          if (!(action && now < actionUntil)) {
            markStart = now;
            markUntil = now + 420;
          }
        }
        if (typed.length === full.length) holdUntil = now + 4000;
      } else if (mode === "speak" && holdUntil && typed.length === full.length && now >= holdUntil) {
        holdUntil = 0;
        setMode("idle");
      }
    }

    function setMode(next) {
      mode = next;
      modeAt = clock();
      if (next !== "speak") {
        mouth = "mouth_shut";
        mouthBlend = 0;
      }
      if (next === "think") setDialog("...", "think");
      if (next === "listen") {
        holdUntil = 0;
        setDialog("", "user");
      }
    }

    function frame() {
      var now = clock();
      var dt = now - last;
      if (dt >= FRAME) {
        var steps = Math.min(30, Math.floor(dt / FRAME));
        var s;
        for (s = 0; s < steps; s += 1) {
          last += FRAME;
          tick(last);
        }
      }
      draw(clock());
      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
    draw(clock());

    return {
      setMode: setMode,
      heard: function (text) {
        setDialog(text, "user");
      },
      speak: function (text, nextAction) {
        full = text || "";
        typed = "";
        holdUntil = 0;
        pinned = true;
        mouth = "mouth_shut";
        mouthNext = "mouth_shut";
        mouthBlend = 0;
        typeAt = clock();
        action = nextAction || "";
        var now = clock();
        if (action) {
          markStart = now;
          markUntil = now + 2000;
          actionUntil = now + 2000;
        } else {
          actionUntil = 0;
          markUntil = 0;
        }
        setMode("speak");
      },
      fail: function (text) {
        full = "";
        typed = "";
        action = "";
        actionUntil = 0;
        markUntil = 0;
        setMode("idle");
        setDialog(text || "", "speak");
      },
      scroll: function (delta) {
        pinned = false;
        dialog.scrollTop += delta;
      },
      lockBlink: function (name) {
        blinkLock = name || "";
      },
    };
  }

  window.createStage = createStage;
})();
