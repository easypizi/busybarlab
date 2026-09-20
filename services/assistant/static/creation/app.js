(function () {
  var API = /github\.io$/.test(location.hostname)
    ? "https://toy-lair-assistant-e9003db7d945.herokuapp.com"
    : "";
  var TOKEN_KEY = "assistantToken";
  var STORAGE_STATUS = {
    secure: "paired via secure",
    plain: "storage: plain",
    local: "storage: local",
  };
  var token = "";
  var items = [];
  var selected = 0;
  var micStream = null;
  var micWait = null;
  var recorder = null;
  var chunks = [];
  var lastEvent = "";
  var storageSource = "";
  var pairTimer = null;
  var recWanted = false;
  var peekOpen = false;
  var stopWatch = null;
  var MIME_TYPES = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "",
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(text) {
    $("status").textContent = text;
  }

  function setReply(text) {
    var reply = $("reply");
    reply.textContent = text;
    if ((text || "").length > 120) reply.classList.add("long");
    else reply.classList.remove("long");
    reply.scrollTop = 0;
  }

  function replyOverflows() {
    var reply = $("reply");
    return reply.scrollHeight > reply.clientHeight + 4;
  }

  function scrollReply(delta) {
    $("reply").scrollTop += delta;
  }

  function showPair(code) {
    $("pair").textContent = code ? code : "";
  }

  function refreshLog() {
    var parts = [];
    if (storageSource) parts.push("storage: " + storageSource);
    if (lastEvent) parts.push(lastEvent);
    $("event-log").textContent = parts.join(" · ");
  }

  function setStorageSource(name) {
    storageSource = name || "";
    refreshLog();
  }

  function logEvent(name) {
    lastEvent = name;
    refreshLog();
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
        body: JSON.stringify({ event: String(event || ""), detail: String(detail || "") }),
      }).catch(function () {});
    } catch (err) {}
  }

  function clipName(mime) {
    var lower = String(mime || "").toLowerCase();
    if (lower.indexOf("ogg") >= 0) return "clip.ogg";
    if (lower.indexOf("mp4") >= 0 || lower.indexOf("m4a") >= 0) return "clip.m4a";
    if (lower.indexOf("webm") >= 0) return "clip.webm";
    return "clip.webm";
  }

  function pickMime() {
    if (typeof MediaRecorder === "undefined") return null;
    if (!MediaRecorder.isTypeSupported) return "";
    for (var i = 0; i < MIME_TYPES.length; i++) {
      var mime = MIME_TYPES[i];
      if (!mime || MediaRecorder.isTypeSupported(mime)) return mime;
    }
    return "";
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

  function wrapStore(name, backend) {
    return {
      name: name,
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
    return wrapStore("local", {
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
      list.push(wrapStore("secure", window.creationStorage.secure));
    }
    if (window.creationStorage && window.creationStorage.plain) {
      list.push(wrapStore("plain", window.creationStorage.plain));
    }
    list.push(localStore());
    return list;
  }

  function decodeStored(stored) {
    if (!stored) return "";
    try {
      return atob(stored);
    } catch (err) {
      return "";
    }
  }

  function readToken() {
    var list = stores();
    var i = 0;
    function next() {
      if (i >= list.length) return Promise.resolve({ token: "", source: "" });
      var store = list[i++];
      return store
        .getItem(TOKEN_KEY)
        .then(function (stored) {
          var value = decodeStored(stored);
          if (value) return { token: value, source: store.name };
          return next();
        })
        .catch(function () {
          return next();
        });
    }
    return next();
  }

  function writeToken(value) {
    var encoded = btoa(value);
    return Promise.all(
      stores().map(function (store) {
        return store.setItem(TOKEN_KEY, encoded).catch(function () {});
      })
    ).then(function () {
      return readToken();
    });
  }

  function applyTokenResult(result, fallback) {
    token = result.token || fallback || "";
    if (result.source) {
      setStorageSource(result.source);
      setStatus(STORAGE_STATUS[result.source] || "storage: " + result.source);
      return;
    }
    setStorageSource("failed");
    setStatus("storage failed");
  }

  function storeToken(value) {
    return writeToken(value).then(function (result) {
      applyTokenResult(result, value);
      return token;
    });
  }

  function clearToken() {
    token = "";
    return Promise.all(
      stores().map(function (store) {
        return store.removeItem(TOKEN_KEY).catch(function () {});
      })
    ).then(function () {
      setStorageSource("");
    });
  }

  function loadToken() {
    return waitForBridge().then(function () {
      var q = new URLSearchParams(window.location.search).get("token");
      if (q) return storeToken(q);
      return readToken().then(function (result) {
        if (result.token) applyTokenResult(result, "");
        return token;
      });
    });
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
    setPeek(false);
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
              return storeToken(body.token).then(function () {
                loadToday();
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

  function rejectIfUnauthorized(res) {
    if (res.status !== 401) return Promise.resolve(res);
    return clearToken().then(function () {
      startPairing();
      throw new Error("pairing required");
    });
  }

  function setPeek(open) {
    peekOpen = !!open;
    $("peek").hidden = !peekOpen;
    document.body.classList.toggle("peek-open", peekOpen);
  }

  function togglePeek() {
    setPeek(!peekOpen);
    if (peekOpen) render();
  }

  function selectItem(index) {
    selected = index;
    render();
  }

  function updateCount() {
    $("count").textContent = items.length ? items.length + " today" : "nothing today";
  }

  function render() {
    var list = $("list");
    list.innerHTML = "";
    if (!items.length) {
      var empty = document.createElement("li");
      empty.textContent = "no items today";
      list.appendChild(empty);
      return;
    }
    items.forEach(function (item, index) {
      var li = document.createElement("li");
      if (index === selected) li.className = "selected";
      var kind = document.createElement("div");
      kind.className = "kind";
      kind.textContent = item.kind + (item.when ? "  " + item.when : "");
      var title = document.createElement("div");
      title.textContent = item.title;
      li.appendChild(kind);
      li.appendChild(title);
      li.addEventListener("touchstart", function () {
        selectItem(index);
      });
      li.addEventListener("click", function () {
        selectItem(index);
      });
      list.appendChild(li);
    });
    var chosen = list.querySelector(".selected");
    if (chosen && chosen.scrollIntoView) {
      chosen.scrollIntoView({ block: "nearest" });
    }
  }

  function loadToday() {
    if (!token) {
      startPairing();
      return;
    }
    fetch(API + "/api/today", { headers: headers() })
      .then(rejectIfUnauthorized)
      .then(function (res) {
        if (!res.ok) throw new Error("today " + res.status);
        return res.json();
      })
      .then(function (data) {
        items = data.items || [];
        selected = 0;
        updateCount();
        render();
      })
      .catch(function (err) {
        setStatus(String(err.message || err));
      });
  }

  function setGateText(text) {
    $("tap-gate").textContent = text;
  }

  function showTapGate() {
    $("tap-gate").hidden = false;
    setGateText("tap once for mic");
    setStatus("tap once for mic");
  }

  function hideTapGate() {
    $("tap-gate").hidden = true;
  }

  function enableMic() {
    if (micStream) return Promise.resolve(micStream);
    if (micWait) return micWait;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus("no getUserMedia (need HTTPS)");
      return Promise.reject(new Error("no mic"));
    }
    setGateText("arming mic");
    setStatus("arming mic");
    beacon("mic ask", "");
    var pending = navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      micStream = stream;
      hideTapGate();
      var tracks = stream.getAudioTracks ? stream.getAudioTracks().length : 0;
      beacon("mic ok", String(tracks));
      return stream;
    });
    var timed = new Promise(function (_, reject) {
      setTimeout(function () {
        var err = new Error("mic timeout");
        err.name = "TimeoutError";
        reject(err);
      }, 8000);
    });
    micWait = Promise.race([pending, timed]).then(
      function (stream) {
        micWait = null;
        return stream;
      },
      function (err) {
        micWait = null;
        throw err;
      }
    );
    return micWait;
  }

  function beginRecorder() {
    if (typeof MediaRecorder === "undefined") {
      setStatus("no MediaRecorder");
      beacon("recorder err", "no MediaRecorder");
      recWanted = false;
      document.body.classList.remove("recording");
      return;
    }
    chunks = [];
    try {
      var mime = pickMime();
      recorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
      recorder.ondataavailable = function (ev) {
        if (ev.data && ev.data.size) chunks.push(ev.data);
        setStatus("recording · " + chunks.length + " chunks");
      };
      recorder.start(250);
      setStatus("recording · 0 chunks");
      beacon("recorder start", recorder.mimeType || mime || "");
    } catch (err) {
      setStatus("rec: " + (err.name || err));
      beacon("recorder err", err.name || String(err));
      recWanted = false;
      document.body.classList.remove("recording");
    }
  }

  function startRec(fromGesture) {
    recWanted = true;
    setPeek(false);
    document.body.classList.add("recording");
    if (!fromGesture && !micStream) {
      recWanted = false;
      document.body.classList.remove("recording");
      showTapGate();
      beacon("need tap", "");
      return;
    }
    setStatus("arming mic");
    enableMic()
      .then(function () {
        if (!recWanted) {
          beacon("end before mic", "");
          return;
        }
        beginRecorder();
      })
      .catch(function (err) {
        recWanted = false;
        document.body.classList.remove("recording");
        var name = (err && err.name) || String(err && err.message) || "error";
        if (name === "TimeoutError" || (err && err.message) === "mic timeout") {
          setStatus("mic timeout");
          setGateText("mic timeout · tap again");
          $("tap-gate").hidden = false;
          beacon("mic timeout", name);
          return;
        }
        setStatus("mic: " + name);
        beacon("mic err", name);
        showTapGate();
        setGateText("mic: " + name);
      });
  }

  function sendClip(blob, mime) {
    if (!blob.size) {
      setStatus("empty clip (0 bytes)");
      beacon("empty clip", mime || "");
      return;
    }
    var body = new FormData();
    body.append("audio", blob, clipName(mime));
    setStatus("sending");
    beacon("blob", blob.size + " " + (mime || ""));
    fetch(API + "/api/voice", { method: "POST", headers: headers(), body: body })
      .then(rejectIfUnauthorized)
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.detail || res.status);
          return data;
        });
      })
      .then(function (data) {
        setReply(data.reply || "");
        setStatus(data.transcript || "ok");
        if (data.audio_base64) {
          var audio = new Audio("data:audio/mpeg;base64," + data.audio_base64);
          audio.play();
        }
        loadToday();
      })
      .catch(function (err) {
        var text = String(err.message || err);
        setStatus(text);
        beacon("voice err", text);
      });
  }

  function finishStop(reason) {
    if (stopWatch) {
      clearTimeout(stopWatch);
      stopWatch = null;
    }
    if (!recorder) {
      document.body.classList.remove("recording");
      return;
    }
    var mime = recorder.mimeType || "audio/webm";
    var blob = new Blob(chunks, { type: mime });
    recorder = null;
    document.body.classList.remove("recording");
    if (reason === "stop timeout") {
      setStatus("stop timeout");
      beacon("stop timeout", String(blob.size));
      if (!blob.size) return;
    }
    sendClip(blob, mime);
  }

  function stopRec() {
    recWanted = false;
    if (!recorder) {
      document.body.classList.remove("recording");
      return;
    }
    recorder.onstop = function () {
      finishStop("onstop");
    };
    try {
      recorder.stop();
    } catch (err) {
      finishStop("stop timeout");
      return;
    }
    stopWatch = setTimeout(function () {
      finishStop("stop timeout");
    }, 2000);
  }

  function onUserTap(ev) {
    if (ev) ev.preventDefault();
    setGateText("arming mic");
    enableMic()
      .then(function () {
        hideTapGate();
        var status = $("status").textContent;
        if (status === "tap once for mic" || status === "arming mic" || status === "mic timeout") {
          setStatus("hold PTT");
        }
      })
      .catch(function (err) {
        var name = (err && err.name) || String(err && err.message) || "error";
        $("tap-gate").hidden = false;
        if (name === "TimeoutError" || (err && err.message) === "mic timeout") {
          setGateText("mic timeout · tap again");
          setStatus("mic timeout");
          beacon("mic timeout", name);
          return;
        }
        setGateText("mic: " + name);
        setStatus("mic: " + name);
        beacon("mic err", name);
      });
  }

  document.body.addEventListener("touchstart", onUserTap, { passive: false });
  document.body.addEventListener("click", onUserTap);

  window.addEventListener("scrollUp", function () {
    logEvent("scrollUp");
    if (recWanted) return;
    if (!peekOpen && replyOverflows() && $("reply").scrollTop > 0) {
      scrollReply(-40);
      return;
    }
    if (!peekOpen) {
      setPeek(true);
      render();
      return;
    }
    if (selected === 0) {
      setPeek(false);
      return;
    }
    selected = Math.max(0, selected - 1);
    render();
  });
  window.addEventListener("scrollDown", function () {
    logEvent("scrollDown");
    if (recWanted) return;
    if (!peekOpen && replyOverflows()) {
      var reply = $("reply");
      if (reply.scrollTop + reply.clientHeight < reply.scrollHeight - 2) {
        scrollReply(40);
        return;
      }
    }
    if (!peekOpen) {
      setPeek(true);
      render();
      return;
    }
    selected = Math.min(Math.max(items.length - 1, 0), selected + 1);
    render();
  });
  window.addEventListener("sideClick", function () {
    logEvent("sideClick");
    beacon("sideClick", "");
    if (recWanted) return;
    togglePeek();
  });
  window.addEventListener("longPressStart", function () {
    logEvent("longPressStart");
    beacon("longPressStart", "");
    startRec();
  });
  window.addEventListener("longPressEnd", function () {
    logEvent("longPressEnd");
    beacon("longPressEnd", "");
    stopRec();
  });

  function bindHold(el) {
    if (!el) return;
    el.addEventListener(
      "touchstart",
      function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        startRec(true);
      },
      { passive: false }
    );
    el.addEventListener(
      "touchend",
      function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        stopRec();
      },
      { passive: false }
    );
    el.addEventListener(
      "touchcancel",
      function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        stopRec();
      },
      { passive: false }
    );
    el.addEventListener("mousedown", function (ev) {
      ev.preventDefault();
      startRec(true);
    });
    el.addEventListener("mouseup", function (ev) {
      ev.preventDefault();
      stopRec();
    });
  }
  bindHold($("rec"));

  loadToken()
    .then(function () {
      render();
      if (token) loadToday();
      else startPairing();
    })
    .catch(function () {
      startPairing();
    });
})();
