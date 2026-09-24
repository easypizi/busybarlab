(function () {
  var API = /github\.io$/.test(location.hostname)
    ? "https://toy-lair-assistant-e9003db7d945.herokuapp.com"
    : "";
  var TOKEN_KEY = "assistantToken";
  var STATE_KEY = "carlosState";
  var rules = window.CARLOS_RULES;
  var token = "";
  var state = {};
  var catalog = null;
  var byDate = {};
  var cursor = rules.CYCLE_START;
  var choiceIndex = 0;
  var racePick = false;
  var raceSide = "wed";
  var helpOpen = false;
  var helpSections = null;
  var voiceOpen = false;
  var listening = false;
  var saveError = false;
  var sttWatch = null;
  var pairTimer = null;
  var spineStop = "";

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(text) {
    $("status").textContent = text;
  }

  var stage = window.createStage($("stage"), $("dialog"), "carlos", {
    onIdle: function () {
      if (!listening) showVoice(false);
    },
  });

  function showVoice(on) {
    voiceOpen = !!on;
    document.body.classList.toggle("voice", voiceOpen);
  }

  function headers() {
    return { "X-Assistant-Token": token };
  }

  function beacon(event, detail) {
    if (!token) return;
    try {
      fetch(API + "/api/client-log", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, headers()),
        body: JSON.stringify({ event: "carlos " + String(event || ""), detail: String(detail || "") }),
      }).catch(function () {});
    } catch (err) {}
  }

  function encodeB64(text) {
    return btoa(unescape(encodeURIComponent(text)));
  }

  function decodeB64(stored) {
    if (!stored) return "";
    try {
      return decodeURIComponent(escape(atob(stored)));
    } catch (err) {
      try {
        return atob(stored);
      } catch (again) {
        return "";
      }
    }
  }

  function needsBridge() {
    if (window.creationStorage) return false;
    if (typeof PluginMessageHandler !== "undefined") return true;
    return /Android/i.test(navigator.userAgent || "");
  }

  function waitForBridge() {
    if (window.creationStorage || !needsBridge()) return Promise.resolve();
    return new Promise(function (resolve) {
      var started = Date.now();
      var timer = setInterval(function () {
        if (window.creationStorage || Date.now() - started >= 3000) {
          clearInterval(timer);
          resolve();
        }
      }, 50);
    });
  }

  function wrapStore(backend) {
    return {
      getItem: function (key) {
        try {
          return Promise.resolve(backend.getItem(key)).catch(function () {
            return null;
          });
        } catch (err) {
          return Promise.resolve(null);
        }
      },
      setItem: function (key, value) {
        try {
          return Promise.resolve(backend.setItem(key, value));
        } catch (err) {
          return Promise.reject(err);
        }
      },
      removeItem: function (key) {
        try {
          return Promise.resolve(backend.removeItem(key));
        } catch (err) {
          return Promise.reject(err);
        }
      },
    };
  }

  function localStore() {
    return wrapStore({
      getItem: function (key) {
        try {
          return window.localStorage.getItem(key);
        } catch (err) {
          return null;
        }
      },
      setItem: function (key, value) {
        window.localStorage.setItem(key, value);
      },
      removeItem: function (key) {
        window.localStorage.removeItem(key);
      },
    });
  }

  function stores() {
    var list = [];
    if (window.creationStorage && window.creationStorage.secure) {
      list.push(wrapStore(window.creationStorage.secure));
    }
    if (window.creationStorage && window.creationStorage.plain) {
      list.push(wrapStore(window.creationStorage.plain));
    }
    list.push(localStore());
    return list;
  }

  function readKey(key) {
    var list = stores();
    var i = 0;
    function next() {
      if (i >= list.length) return Promise.resolve("");
      return list[i++]
        .getItem(key)
        .then(function (stored) {
          var value = decodeB64(stored);
          if (value) return value;
          return next();
        })
        .catch(function () {
          return next();
        });
    }
    return next();
  }

  function writeKey(key, value) {
    var encoded = encodeB64(value);
    return Promise.all(
      stores().map(function (store) {
        return store.setItem(key, encoded).catch(function () {});
      })
    );
  }

  function loadToken() {
    return waitForBridge().then(function () {
      var q = new URLSearchParams(window.location.search).get("token");
      if (q) return writeKey(TOKEN_KEY, q).then(function () { token = q; });
      return readKey(TOKEN_KEY).then(function (value) { token = value || ""; });
    });
  }

  function clearToken() {
    token = "";
    return Promise.all(
      stores().map(function (store) {
        return store.removeItem(TOKEN_KEY).catch(function () {});
      })
    );
  }

  function loadState() {
    return readKey(STATE_KEY).then(function (raw) {
      if (!raw) return;
      try {
        var data = JSON.parse(raw);
        if (data && typeof data === "object") state = data;
      } catch (err) {}
    });
  }

  function saveState() {
    return writeKey(STATE_KEY, JSON.stringify(state));
  }

  function showPair(code) {
    $("pair").textContent = code ? code : "";
  }

  function stopPairing() {
    if (pairTimer) {
      clearInterval(pairTimer);
      pairTimer = null;
    }
    showPair("");
  }

  function startPairing() {
    stopPairing();
    setStatus("pairing");
    fetch(API + "/api/pair/start", { method: "POST" })
      .then(function (res) {
        if (!res.ok) throw new Error("pair " + res.status);
        return res.json();
      })
      .then(function (data) {
        showPair(data.code);
        setStatus("enter code on install page");
        pairTimer = setInterval(function () {
          fetch(API + "/api/pair/claim?secret=" + encodeURIComponent(data.secret))
            .then(function (res) {
              if (res.status === 404) {
                startPairing();
                return null;
              }
              if (!res.ok) throw new Error("claim " + res.status);
              return res.json();
            })
            .then(function (body) {
              if (!body || body.status !== "approved" || !body.token) return;
              stopPairing();
              token = body.token;
              return writeKey(TOKEN_KEY, body.token).then(function () {
                pullLog(cursor);
                render();
              });
            })
            .catch(function (err) {
              setStatus(String(err.message || err));
            });
        }, 2000);
      })
      .catch(function (err) {
        setStatus(String(err.message || err));
      });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function addExercise(parent, name, sets, cues) {
    parent.appendChild(el("p", "ex-name", name));
    if (sets) parent.appendChild(el("p", "ex-sets", sets));
    if (cues) parent.appendChild(el("p", "ex-cues", cues));
  }

  function renderLocked(text) {
    var card = $("card");
    card.innerHTML = "";
    card.appendChild(el("p", "title", text));
  }

  function renderChoice(day) {
    var card = $("card");
    var options = rules.choiceOptions(day);
    card.appendChild(el("p", "meta", day.weekdayRu + " · " + day.date));
    card.appendChild(el("p", "title", day.title));
    if (day.deloadNote) card.appendChild(el("p", "block", day.deloadNote));
    options.forEach(function (option, index) {
      var row = el("div", "option" + (index === choiceIndex ? " selected" : ""));
      row.appendChild(el("p", "ex-name", option.name));
      if (option.cues) row.appendChild(el("p", "ex-cues", option.cues));
      card.appendChild(row);
    });
    if (spineStop) card.appendChild(el("p", "stop", spineStop));
    var line = rules.logLine(state["log:" + day.date]);
    if (line) card.appendChild(el("p", "log", line));
    if (saveError) card.appendChild(el("p", "miss", "запись не сохранилась"));
    var help = el("button", "row", "справка");
    help.type = "button";
    help.setAttribute("data-act", "help");
    card.appendChild(help);
  }

  function renderDay(day) {
    var card = $("card");
    var view = rules.present(day, state);
    var meta = [day.weekdayRu, day.date, "нед. " + day.week, day.block];
    if (day.deload) meta.push("разгрузка");
    card.appendChild(el("p", "meta", meta.join(" · ")));
    card.appendChild(el("p", "title", day.title));
    if (day.duration) card.appendChild(el("p", "duration", day.duration));
    if (!view.replaced) {
      if (day.intro) card.appendChild(el("p", "", day.intro));
      if (day.warmup) card.appendChild(el("p", "cues", day.warmup));
      if (day.deloadNote) card.appendChild(el("p", "block", day.deloadNote));
    }
    if (view.raceText) card.appendChild(el("p", "block", view.raceText));
    if (view.pick) {
      addExercise(card, view.pick.name, view.pick.duration || "", view.pick.cues || "");
    } else if (!view.hideExercises) {
      (day.exercises || []).forEach(function (item) {
        addExercise(card, item.name, item.sets || "", item.cues || "");
      });
    }
    if (view.volume) card.appendChild(el("p", "block", view.volume));
    if (racePick) {
      ["wed", "sat"].forEach(function (side) {
        var label = side === "wed" ? "среда" : "суббота";
        var row = el("div", "option" + (raceSide === side ? " selected" : ""), label);
        card.appendChild(row);
      });
    }
    if (spineStop) card.appendChild(el("p", "stop", spineStop));
    var line = rules.logLine(state["log:" + day.date]);
    if (line) card.appendChild(el("p", "log", line));
    if (saveError) card.appendChild(el("p", "miss", "запись не сохранилась"));
    var raceName = view.raceSide === "wed" ? "ср" : view.raceSide === "sat" ? "сб" : "";
    var race = el("button", "row", raceName ? "гонка · " + raceName : "гонка");
    race.type = "button";
    race.setAttribute("data-act", "race");
    card.appendChild(race);
    var help = el("button", "row", "справка");
    help.type = "button";
    help.setAttribute("data-act", "help");
    card.appendChild(help);
  }

  function renderHelp() {
    var box = $("help");
    box.innerHTML = "";
    var back = el("button", "row", "день");
    back.type = "button";
    back.setAttribute("data-act", "back");
    box.appendChild(back);
    (helpSections || []).forEach(function (section) {
      box.appendChild(el("h2", "", section.title));
      String(section.body || "").split("\n").forEach(function (line) {
        var trimmed = line.trim();
        if (!trimmed) return;
        var item = trimmed.indexOf("- ") === 0;
        box.appendChild(el("p", item ? "item" : "", item ? trimmed.slice(2) : trimmed));
      });
    });
  }

  function render() {
    var today = rules.todayISO();
    var screen = rules.screenFor(today);
    document.body.classList.toggle("help", helpOpen && screen === "card");
    var card = $("card");
    card.innerHTML = "";
    if (screen === "early") {
      renderLocked(rules.EARLY_TEXT);
      return;
    }
    if (screen === "late") {
      renderLocked(rules.LATE_TEXT);
      return;
    }
    var day = byDate[cursor];
    if (!day) {
      renderLocked(cursor);
      return;
    }
    if (rules.needsChoice(day, state) && !racePick) renderChoice(day);
    else renderDay(day);
    if (helpOpen) renderHelp();
  }

  function loadHelp() {
    if (helpSections) return Promise.resolve();
    return fetch("help.json")
      .then(function (res) { return res.json(); })
      .then(function (data) { helpSections = data || []; })
      .catch(function () { helpSections = []; });
  }

  function pullLog(date) {
    if (!token || !date) return;
    fetch(API + "/api/carlos/log?date=" + encodeURIComponent(date), { headers: headers() })
      .then(function (res) {
        if (res.status === 401) return null;
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.entry) return;
        state["log:" + date] = data.entry;
        saveState();
        if (cursor === date) render();
      })
      .catch(function () {});
  }

  function loadDays() {
    return fetch("days.json")
      .then(function (res) {
        if (!res.ok) throw new Error("days " + res.status);
        return res.json();
      })
      .then(function (data) {
        catalog = data;
        spineStop = (data.spine && data.spine.stop) || "";
        byDate = {};
        (data.days || []).forEach(function (day) { byDate[day.date] = day; });
        var today = rules.todayISO();
        if (rules.screenFor(today) === "card") cursor = today;
      });
  }

  function hasVoiceBridge() {
    return typeof CreationVoiceHandler !== "undefined";
  }

  function speak(text) {
    if (!text || typeof PluginMessageHandler === "undefined") return;
    PluginMessageHandler.postMessage(
      JSON.stringify({ message: text, useLLM: false, wantsR1Response: true })
    );
  }

  function sendText(text) {
    var day = byDate[cursor];
    if (!day) return;
    var view = rules.present(day, state);
    setStatus("sending");
    stage.setMode("think");
    showVoice(true);
    beacon("text", text);
    fetch(API + "/api/carlos/log", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, headers()),
      body: JSON.stringify({
        text: text,
        date: day.date,
        sessionId: day.sessionId,
        title: day.title,
        exercises: view.names,
      }),
    })
      .then(function (res) {
        if (res.status === 401) {
          clearToken().then(startPairing);
          throw new Error("pairing required");
        }
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error("save failed");
          return data;
        });
      })
      .then(function (data) {
        saveError = false;
        state["log:" + day.date] = data.entry;
        saveState();
        setStatus(day.date);
        stage.speak(data.reply || "", data.action || "logged");
        speak(data.reply || "");
        render();
      })
      .catch(function (err) {
        if (String(err.message || err) === "pairing required") return;
        saveError = true;
        showVoice(false);
        stage.fail("");
        setStatus("запись не сохранилась");
        beacon("text err", String(err.message || err));
        render();
      });
  }

  function startRec() {
    if (listening) return;
    if (rules.screenFor(rules.todayISO()) !== "card") return;
    helpOpen = false;
    if (!token) {
      startPairing();
      return;
    }
    if (!hasVoiceBridge()) {
      setStatus("no voice bridge (open on r1)");
      beacon("no voice bridge", "");
      return;
    }
    listening = true;
    document.body.classList.add("recording");
    showVoice(true);
    stage.setMode("listen");
    setStatus("listening");
    CreationVoiceHandler.postMessage("start");
    beacon("stt start", "");
  }

  function stopRec() {
    if (!listening) return;
    document.body.classList.remove("recording");
    setStatus("transcribing");
    CreationVoiceHandler.postMessage("stop");
    if (sttWatch) clearTimeout(sttWatch);
    sttWatch = setTimeout(function () {
      listening = false;
      showVoice(false);
      setStatus("stt timeout");
      beacon("stt timeout", "");
    }, 15000);
  }

  window.onPluginMessage = function (data) {
    if (typeof data === "string") {
      try { data = JSON.parse(data); } catch (err) { return; }
    }
    if (!data) return;
    if (data.type === "sttStarted") {
      setStatus("listening");
      return;
    }
    if (data.type !== "sttEnded") return;
    if (sttWatch) {
      clearTimeout(sttWatch);
      sttWatch = null;
    }
    listening = false;
    document.body.classList.remove("recording");
    var text = String(data.transcript || "").trim();
    if (!text) {
      showVoice(false);
      stage.fail("");
      setStatus("heard nothing");
      beacon("stt empty", "");
      return;
    }
    stage.heard(text);
    sendText(text);
  };

  function onWheel(dir) {
    if (listening) return;
    if (voiceOpen) {
      var reply = $("dialog");
      if (reply.scrollHeight > reply.clientHeight + 4) reply.scrollTop += dir * 16;
      return;
    }
    if (helpOpen) {
      $("help").scrollTop += dir * 40;
      return;
    }
    if (rules.screenFor(rules.todayISO()) !== "card") return;
    var day = byDate[cursor];
    if (day && rules.needsChoice(day, state)) {
      var count = rules.choiceOptions(day).length || 1;
      choiceIndex = (choiceIndex + dir + count) % count;
      render();
      return;
    }
    if (racePick) {
      raceSide = raceSide === "wed" ? "sat" : "wed";
      render();
      return;
    }
    var next = rules.shiftCursor(cursor, dir);
    if (next === cursor) return;
    cursor = next;
    choiceIndex = 0;
    saveError = false;
    render();
    pullLog(cursor);
  }

  $("card").addEventListener("click", function (ev) {
    var row = ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!row || listening) return;
    var act = row.getAttribute("data-act");
    if (act === "help") {
      helpOpen = true;
      racePick = false;
      loadHelp().then(render);
      return;
    }
    if (act === "back") {
      helpOpen = false;
      render();
      return;
    }
    if (act === "race") {
      var key = rules.raceKey(byDate[cursor]);
      if (state[key]) {
        delete state[key];
        racePick = false;
        saveState();
      } else {
        racePick = true;
        raceSide = "wed";
        helpOpen = false;
      }
      render();
    }
  });

  $("help").addEventListener("click", function (ev) {
    var row = ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!row || row.getAttribute("data-act") !== "back") return;
    helpOpen = false;
    render();
  });

  window.addEventListener("scrollUp", function () { onWheel(-1); });
  window.addEventListener("scrollDown", function () { onWheel(1); });
  window.addEventListener("sideClick", function () {
    beacon("sideClick", "");
    if (listening) return;
    if (helpOpen) {
      helpOpen = false;
      render();
      return;
    }
    var day = byDate[cursor];
    if (!day) return;
    if (rules.needsChoice(day, state)) {
      var options = rules.choiceOptions(day);
      var pick = options[choiceIndex] || options[0];
      if (!pick) return;
      state["friday:" + day.date] = pick.id;
      saveState();
      render();
      return;
    }
    if (racePick) {
      state[rules.raceKey(day)] = raceSide;
      racePick = false;
      saveState();
      render();
    }
  });
  window.addEventListener("longPressStart", function () {
    beacon("longPressStart", "");
    startRec();
  });
  window.addEventListener("longPressEnd", function () {
    beacon("longPressEnd", "");
    stopRec();
  });

  function bindHold(node) {
    if (!node) return;
    node.addEventListener("touchstart", function (ev) {
      ev.preventDefault();
      startRec();
    }, { passive: false });
    node.addEventListener("touchend", function (ev) {
      ev.preventDefault();
      stopRec();
    }, { passive: false });
    node.addEventListener("mousedown", function (ev) {
      ev.preventDefault();
      startRec();
    });
    node.addEventListener("mouseup", function (ev) {
      ev.preventDefault();
      stopRec();
    });
  }
  bindHold($("stage"));

  loadToken()
    .then(loadState)
    .then(loadDays)
    .then(function () {
      render();
      if (token) pullLog(cursor);
      else startPairing();
    })
    .catch(function (err) {
      setStatus(String(err.message || err));
    });
})();
