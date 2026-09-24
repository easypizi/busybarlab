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
  var lastEvent = "";
  var storageSource = "";
  var pairTimer = null;
  var peekOpen = false;
  var listening = false;
  var sttWatch = null;

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(text) {
    $("status").textContent = text;
  }

  var stage = window.createStage($("stage"), $("dialog"), "paco");

  function setReply(text) {
    stage.fail(text);
  }

  function replyOverflows() {
    var box = $("dialog");
    return box.scrollHeight > box.clientHeight + 4;
  }

  function scrollReply(delta) {
    stage.scroll(delta);
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
        body: JSON.stringify({ event: "paco " + String(event || ""), detail: String(detail || "") }),
      }).catch(function () {});
    } catch (err) {}
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
                loadInbox();
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

  function openInbox() {
    setPeek(true);
    loadInbox();
  }

  function togglePeek() {
    if (peekOpen) {
      setPeek(false);
      return;
    }
    openInbox();
  }

  function selectItem(index) {
    selected = index;
    render();
  }

  function updateCount(count) {
    var n = typeof count === "number" ? count : items.length;
    $("count").textContent = n ? n + " inbox" : "inbox empty";
  }

  function rowKind(item) {
    if (item.path) return item.path;
    var bits = [];
    if (typeof item.age_hours === "number") bits.push(item.age_hours + "h");
    if (item.tags && item.tags.indexOf("to-process") !== -1) bits.push("#to-process");
    return bits.join(" ");
  }

  function render() {
    var list = $("list");
    list.innerHTML = "";
    if (!items.length) {
      var empty = document.createElement("li");
      empty.textContent = "inbox empty";
      list.appendChild(empty);
      return;
    }
    items.forEach(function (item, index) {
      var li = document.createElement("li");
      if (index === selected) li.className = "selected";
      var kind = document.createElement("div");
      kind.className = "kind";
      kind.textContent = rowKind(item);
      var title = document.createElement("div");
      title.textContent = item.title || "";
      li.appendChild(kind);
      li.appendChild(title);
      list.appendChild(li);
    });
    var chosen = list.querySelector(".selected");
    if (chosen && chosen.scrollIntoView) {
      chosen.scrollIntoView({ block: "nearest" });
    }
    if (chosen) {
      var viewTop = list.scrollTop;
      var viewBottom = viewTop + list.clientHeight;
      if (chosen.offsetTop < viewTop) list.scrollTop = chosen.offsetTop;
      else if (chosen.offsetTop + chosen.offsetHeight > viewBottom) {
        list.scrollTop = chosen.offsetTop + chosen.offsetHeight - list.clientHeight;
      }
    }
  }

  function loadInbox() {
    if (!token) {
      startPairing();
      return;
    }
    fetch(API + "/api/paco/inbox", { headers: headers() })
      .then(rejectIfUnauthorized)
      .then(function (res) {
        if (!res.ok) throw new Error("inbox " + res.status);
        return res.json();
      })
      .then(function (data) {
        items = data.items || [];
        selected = 0;
        updateCount(typeof data.count === "number" ? data.count : items.length);
        render();
      })
      .catch(function (err) {
        setStatus(String(err.message || err));
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
    setStatus("sending");
    stage.setMode("think");
    beacon("text", text);
    fetch(API + "/api/paco/text", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, headers()),
      body: JSON.stringify({ text: text }),
    })
      .then(rejectIfUnauthorized)
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.detail || res.status);
          return data;
        });
      })
      .then(function (data) {
        setStatus(text);
        stage.speak(data.reply || "", data.action || "");
        speak(data.reply || "");
        var peek = data.peek || {};
        if (peek.kind === "hits") {
          items = peek.items || [];
          selected = 0;
          updateCount(items.length);
          setPeek(true);
          render();
          return;
        }
        setPeek(false);
        if (typeof peek.count === "number") updateCount(peek.count);
        else loadInbox();
      })
      .catch(function (err) {
        var message = String(err.message || err);
        setStatus(message);
        stage.fail(message);
        beacon("text err", message);
      });
  }

  function startRec() {
    if (listening) return;
    if (!hasVoiceBridge()) {
      setStatus("no voice bridge (open on r1)");
      beacon("no voice bridge", "");
      return;
    }
    listening = true;
    setPeek(false);
    document.body.classList.add("recording");
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
      setStatus("stt timeout");
      beacon("stt timeout", "");
    }, 15000);
  }

  window.onPluginMessage = function (data) {
    if (typeof data === "string") {
      try {
        data = JSON.parse(data);
      } catch (err) {
        return;
      }
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
      setStatus("heard nothing");
      stage.fail("heard nothing");
      beacon("stt empty", "");
      return;
    }
    stage.heard(text);
    sendText(text);
  };

  window.addEventListener("scrollUp", function () {
    logEvent("scrollUp");
    if (listening) return;
    if (!peekOpen && replyOverflows() && $("dialog").scrollTop > 0) {
      scrollReply(-16);
      return;
    }
    if (!peekOpen) {
      openInbox();
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
    if (listening) return;
    if (!peekOpen && replyOverflows()) {
      var reply = $("dialog");
      if (reply.scrollTop + reply.clientHeight < reply.scrollHeight - 2) {
        scrollReply(16);
        return;
      }
    }
    if (!peekOpen) {
      openInbox();
      return;
    }
    selected = Math.min(Math.max(items.length - 1, 0), selected + 1);
    render();
  });
  window.addEventListener("sideClick", function () {
    logEvent("sideClick");
    beacon("sideClick", "");
    if (listening) return;
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
        startRec();
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
      startRec();
    });
    el.addEventListener("mouseup", function (ev) {
      ev.preventDefault();
      stopRec();
    });
  }
  bindHold($("stage"));

  loadToken()
    .then(function () {
      render();
      if (token) loadInbox();
      else startPairing();
    })
    .catch(function () {
      startPairing();
    });
})();
