// Wednesday Frogs remote for Flipper Zero + FlipperHTTP Wi-Fi Dev Board.
// Copy this file, flipper_http.js, and busybar_frogs.conf.json to SD:/apps/Scripts/

let eventLoop = require("event_loop");
let gui = require("gui");
let submenuView = require("gui/submenu");
let dialogView = require("gui/dialog");
let loadingView = require("gui/loading");
let storage = require("storage");

let SCRIPT_DIR = "/ext/apps/Scripts";

function asString(value) {
    if (value === undefined) {
        return "";
    }
    if (typeof value === "string") {
        return value;
    }
    let out = "";
    let i = 0;
    while (i < value.length) {
        out += value[i];
        i++;
    }
    return out;
}

function readFile(name) {
    return asString(storage.read(SCRIPT_DIR + "/" + name));
}

let httpErr = "";
let httpSrc = readFile("flipper_http.js");
if (httpSrc === "") {
    httpErr = "missing flipper_http.js";
} else {
    eval(httpSrc);
}

function loadConfig() {
    let raw = readFile("busybar_frogs.conf.json");
    if (raw === "") {
        return undefined;
    }
    return JSON.parse(raw);
}

function contains(text, search) {
    if (text === undefined || text === false || search === undefined) {
        return false;
    }
    let s = asString(text);
    let i = 0;
    while (i <= s.length - search.length) {
        let matched = true;
        let j = 0;
        while (j < search.length) {
            if (s[i + j] !== search[j]) {
                matched = false;
                break;
            }
            j++;
        }
        if (matched) {
            return true;
        }
        i++;
    }
    return false;
}

function httpHeaders(cfg) {
    return '{"Content-Type":"application/json","X-API-Token":"' + cfg.token + '"}';
}

function ensureWifi() {
    fhttp.init();
    if (fhttp.ping()) {
        return true;
    }
    return fhttp.connect_wifi();
}

function showResult(views, title, body) {
    views.result.set("header", title);
    views.result.set("text", asString(body));
    gui.viewDispatcher.switchTo(views.result);
}

function drawPayload(views, cfg, payload) {
    gui.viewDispatcher.switchTo(views.loading);
    if (!ensureWifi()) {
        fhttp.deinit();
        showResult(views, "Error", "Wi-Fi board ping failed");
        return;
    }
    let resp = fhttp.post_request_with_headers(
        cfg.base_url + "/display/draw",
        httpHeaders(cfg),
        JSON.stringify(payload)
    );
    fhttp.deinit();
    let text = asString(resp);
    if (resp === false || resp === "" || contains(text, "409") || contains(text, "low priority")) {
        showResult(views, "Error", text === "" ? "draw failed" : text);
        return;
    }
    showResult(views, "OK", text);
}

function clearFrogs(views, cfg) {
    gui.viewDispatcher.switchTo(views.loading);
    if (!ensureWifi()) {
        fhttp.deinit();
        showResult(views, "Error", "Wi-Fi board ping failed");
        return;
    }
    let resp = fhttp.delete_request_with_headers(
        cfg.base_url + "/display/draw?application_name=" + cfg.app,
        httpHeaders(cfg),
        "{}"
    );
    fhttp.deinit();
    let text = asString(resp);
    if (resp === false || resp === "") {
        showResult(views, "Error", "clear failed");
        return;
    }
    showResult(views, "OK", text);
}

function pingBoard(views) {
    gui.viewDispatcher.switchTo(views.loading);
    fhttp.init();
    let ok = fhttp.ping();
    fhttp.deinit();
    if (ok) {
        showResult(views, "OK", "PONG");
    } else {
        showResult(views, "Error", "No PONG from board");
    }
}

let cfg = loadConfig();
let views = {
    loading: loadingView.make(),
    menu: submenuView.makeWith({
        header: "BUSY Frogs",
        items: [
            "Frogs happy",
            "Frogs sad",
            "Clear",
            "Ping board",
            "Exit",
        ],
    }),
    result: dialogView.makeWith(
        {
            header: "BUSY Frogs",
            text: "Ready",
        },
        [{ element: "button", button: "center", text: "Back" }]
    ),
};

if (httpErr !== "") {
    views.result.set("header", "Error");
    views.result.set("text", httpErr);
}

if (cfg === undefined) {
    views.result.set("header", "Error");
    views.result.set("text", "missing busybar_frogs.conf.json");
}

eventLoop.subscribe(views.menu.chosen, function (_sub, index, gui, eventLoop, views, cfg) {
    if (index === 4) {
        eventLoop.stop();
        return;
    }
    if (typeof fhttp === "undefined") {
        showResult(views, "Error", "fhttp missing");
        return;
    }
    if (cfg === undefined && index !== 3) {
        showResult(views, "Error", "missing config");
        return;
    }
    if (index === 0) {
        drawPayload(views, cfg, cfg.happy);
    } else if (index === 1) {
        drawPayload(views, cfg, cfg.sad);
    } else if (index === 2) {
        clearFrogs(views, cfg);
    } else if (index === 3) {
        pingBoard(views);
    }
}, gui, eventLoop, views, cfg);

eventLoop.subscribe(gui.viewDispatcher.navigation, function (_sub, _, gui, views, eventLoop) {
    if (gui.viewDispatcher.currentView === views.menu) {
        eventLoop.stop();
        return;
    }
    gui.viewDispatcher.switchTo(views.menu);
}, gui, views, eventLoop);

if (httpErr !== "" || cfg === undefined) {
    gui.viewDispatcher.switchTo(views.result);
} else {
    gui.viewDispatcher.switchTo(views.menu);
}
eventLoop.run();
