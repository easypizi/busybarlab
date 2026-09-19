(function () {
  var TOKEN_KEY = "assistantToken";
  var token = "";
  var items = [];
  var selected = 0;
  var micStream = null;
  var recorder = null;
  var chunks = [];
  var lastEvent = "";

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(text) {
    $("status").textContent = text;
  }

  function logEvent(name) {
    lastEvent = name;
    $("event-log").textContent = name;
  }

  function headers() {
    return { "X-Assistant-Token": token };
  }

  function loadToken() {
    try {
      if (window.creationStorage && window.creationStorage.plain) {
        var stored = window.creationStorage.plain.getItem(TOKEN_KEY);
        if (stored) token = atob(stored);
      }
    } catch (err) {}
    var q = new URLSearchParams(window.location.search).get("token");
    if (q) {
      token = q;
      try {
        if (window.creationStorage && window.creationStorage.plain) {
          window.creationStorage.plain.setItem(TOKEN_KEY, btoa(q));
        }
      } catch (err) {}
    }
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
      list.appendChild(li);
    });
  }

  function loadToday() {
    if (!token) {
      setStatus("missing token");
      return;
    }
    fetch("/api/today", { headers: headers() })
      .then(function (res) {
        if (!res.ok) throw new Error("today " + res.status);
        return res.json();
      })
      .then(function (data) {
        items = data.items || [];
        selected = 0;
        setStatus(items.length + " items");
        render();
      })
      .catch(function (err) {
        setStatus(String(err.message || err));
      });
  }

  function completeSelected() {
    var item = items[selected];
    if (!item || item.kind !== "task") return;
    fetch("/api/tasks/" + encodeURIComponent(item.id) + "/complete", {
      method: "POST",
      headers: headers(),
    }).then(function (res) {
      if (res.ok) loadToday();
    });
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
        setStatus("mic ready, hold PTT");
        return stream;
      });
  }

  function startRec() {
    if (!micStream) {
      setStatus("tap screen first");
      return;
    }
    chunks = [];
    var mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    recorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
    recorder.ondataavailable = function (ev) {
      if (ev.data && ev.data.size) chunks.push(ev.data);
    };
    recorder.start();
    document.body.classList.add("recording");
    setStatus("recording " + recorder.mimeType);
  }

  function stopRec() {
    if (!recorder) return;
    recorder.onstop = function () {
      document.body.classList.remove("recording");
      var blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      var body = new FormData();
      body.append("audio", blob, "clip.webm");
      setStatus("sending");
      fetch("/api/voice", { method: "POST", headers: headers(), body: body })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error(data.detail || res.status);
            return data;
          });
        })
        .then(function (data) {
          $("reply").textContent = data.reply || "";
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
      enableMic().catch(function () {});
    },
    { passive: false }
  );

  window.addEventListener("scrollUp", function () {
    logEvent("scrollUp");
    selected = Math.max(0, selected - 1);
    render();
  });
  window.addEventListener("scrollDown", function () {
    logEvent("scrollDown");
    selected = Math.min(Math.max(items.length - 1, 0), selected + 1);
    render();
  });
  window.addEventListener("sideClick", function () {
    logEvent("sideClick");
    completeSelected();
  });
  window.addEventListener("longPressStart", function () {
    logEvent("longPressStart");
    startRec();
  });
  window.addEventListener("longPressEnd", function () {
    logEvent("longPressEnd");
    stopRec();
  });

  loadToken();
  render();
  loadToday();
})();
