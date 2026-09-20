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
  var recorder = null;
  var chunks = [];
  var lastEvent = "";
  var storageSource = "";
  var pairTimer = null;
  var recWanted = false;
  var peekOpen = false;

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

  function showTapGate() {
    $("tap-gate").hidden = false;
    setStatus("tap once for mic");
  }

  function hideTapGate() {
    $("tap-gate").hidden = true;
  }

  function enableMic() {
    if (micStream) return Promise.resolve(micStream);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus("no getUserMedia (need HTTPS)");
      return Promise.reject(new Error("no mic"));
    }
    return navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(function (stream) {
        micStream = stream;
        hideTapGate();
        return stream;
      });
  }

  function beginRecorder() {
    chunks = [];
    var mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    recorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
    recorder.ondataavailable = function (ev) {
      if (ev.data && ev.data.size) chunks.push(ev.data);
    };
    recorder.start();
    setStatus("recording");
  }

  function startRec() {
    recWanted = true;
    setPeek(false);
    document.body.classList.add("recording");
    setStatus("arming mic");
    enableMic()
      .then(function () {
        if (!recWanted) return;
        beginRecorder();
      })
      .catch(function () {
        recWanted = false;
        document.body.classList.remove("recording");
        showTapGate();
      });
  }

  function stopRec() {
    recWanted = false;
    if (!recorder) {
      document.body.classList.remove("recording");
      return;
    }
    recorder.onstop = function () {
      document.body.classList.remove("recording");
      var blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      recorder = null;
      if (!blob.size) {
        setStatus("hold PTT");
        return;
      }
      var body = new FormData();
      body.append("audio", blob, "clip.webm");
      setStatus("sending");
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
          setStatus(String(err.message || err));
        });
    };
    recorder.stop();
  }

  document.body.addEventListener(
    "touchstart",
    function (ev) {
      ev.preventDefault();
      enableMic()
        .then(function () {
          hideTapGate();
          if ($("status").textContent === "tap once for mic") setStatus("hold PTT");
        })
        .catch(function () {
          showTapGate();
        });
    },
    { passive: false }
  );

  $("tap-gate").addEventListener(
    "touchstart",
    function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      enableMic()
        .then(function () {
          hideTapGate();
          setStatus("hold PTT");
        })
        .catch(function () {
          showTapGate();
        });
    },
    { passive: false }
  );

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
    if (recWanted) return;
    togglePeek();
  });
  window.addEventListener("longPressStart", function () {
    logEvent("longPressStart");
    startRec();
  });
  window.addEventListener("longPressEnd", function () {
    logEvent("longPressEnd");
    stopRec();
  });

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
