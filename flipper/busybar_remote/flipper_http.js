// Vendored from https://github.com/jblanked/FlipperHTTP (MIT, Author: JBlanked)
// Description: Flipper HTTP API (For use with Flipper Zero and the FlipperHTTP flash: https://github.com/jblanked/FlipperHTTP)
// Global: flipper_http_init, flipper_http_deinit, flipper_http_rx_callback(), flipper_http_send_data, flipper_http_connect_wifi, flipper_http_disconnect_wifi, flipper_http_ping, flipper_http_save_wifi, flipper_http_get_request
// License: MIT
// Author: JBlanked
// File: flipper_http.js

let serial = require("serial");

// Define the global `fhttp` object with all the functions
let fhttp = {
    // Constructor
    init: function () {
        serial.setup("usart", 115200);
    },
    // Deconstructor
    deinit: function () {
        serial.end();
    },
    // Read data from the serial port and return it line by line
    read_data: function (delay_ms) {
        let line = serial.readln(delay_ms);
        let i = 5;
        while (line === undefined && i > 0) {
            line = serial.readln(delay_ms);
            i--;
        }
        return line;
    },
    // Send data to the serial port
    send_data: function (data) {
        if (data === "") {
            return;
        }
        serial.write(data);
    },
    // Clear the incoming serial by up to 10 lines
    clear_buffer: function (search_for_success) {
        let data = this.read_data(100);
        let sdata = this.to_string(data);
        let i = 0;
        // clear all data until we get an expected response
        while (i < 5 &&
            (data !== undefined &&
                (!search_for_success || (search_for_success && !this.includes(sdata, "[SUCCESS]"))) &&
                !this.includes(sdata, "[ERROR]") &&
                !this.includes(sdata, "[INFO]") &&
                !this.includes(sdata, "[PONG]") &&
                !this.includes(sdata, "[DISCONNECTED]") &&
                !this.includes(sdata, "[CONNECTED]") &&
                !this.includes(sdata, "[GET/STARTED]") &&
                !this.includes(sdata, "[GET/END]"))) {
            data = this.read_data(100);
            sdata = this.to_string(data);
            i++;
        }
    },
    // Connect to wifi
    connect_wifi: function () {
        serial.write("[WIFI/CONNECT]");
        let response = this.read_data(500);
        if (response === undefined) {
            return false;
        }
        let sresponse = this.to_string(response);
        this.clear_buffer(true); // Clear the buffer
        return this.includes(sresponse, "[SUCCESS]") || this.includes(sresponse, "[CONNECTED]") || this.includes(sresponse, "[INFO]");
    },
    // Disconnect from wifi
    disconnect_wifi: function () {
        serial.write("[WIFI/DISCONNECT]");
        let response = this.read_data(500);
        if (response === undefined) {
            return false;
        }
        let sresponse = this.to_string(response);
        this.clear_buffer(true); // Clear the buffer
        return this.includes(sresponse, "[DISCONNECTED]") || this.includes(sresponse, "WiFi stop");
    },
    // Send a ping to the board
    ping: function () {
        serial.write("[PING]");
        let response = this.read_data(100);
        if (response === undefined) {
            return false;
        }
        this.clear_buffer(true); // Clear the buffer
        return this.includes(this.to_string(response), "[PONG]");
    },
    // list available commands
    list_commands: function () {
        serial.write("[LIST]");
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // Allow the LED to display while processing
    led_on: function () {
        serial.write("[LED/ON]");
    },
    // Disable the LED from displaying while processing
    led_off: function () {
        serial.write("[LED/OFF]");
    },
    // parse JSON data
    parse_json: function (key, data) {
        serial.write('[PARSE]{"key":"' + key + '","data":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // parse JSON array
    parse_json_array: function (key, index, data) {
        serial.write('[PARSE/ARRAY]{"key":"' + key + '","index":' + index + ',"data":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // Get Wifi network list
    scan_wifi: function () {
        serial.write("[WIFI/SCAN]");
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // Save wifi settings
    save_wifi: function (ssid, password) {
        if (ssid === "" || password === "") {
            return false;
        }
        let command = '[WIFI/SAVE]{"ssid":"' + ssid + '","password":"' + password + '"}';
        serial.write(command);
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[SUCCESS]")) {
            this.clear_buffer(false); // Clear the buffer
            this.clear_buffer(false); // Clear the buffer
            return true;
        }
        else {
            print("Failed to save: " + response);
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
    },
    // Get the IP address of the WiFi Devboard
    ip_address: function () {
        serial.write("[IP/ADDRESS]");
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // Get the IP address of the connected WiFi network
    ip_wifi: function () {
        serial.write("[WIFI/IP]");
        let response = this.read_data(500);
        if (response === undefined) {
            return "";
        }
        return this.to_string(response);
    },
    // Send a GET request to the board
    // I reduced this to return the first line of the response that isnt undefined
    // You'll also get 'out of memory' errors if you try to read/return too much data
    // As mjs is updated, this can be improved
    get_request: function (url) {
        serial.write('[GET]' + url);
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[GET/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[GET/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("GET request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // another GET request but with headers
    get_request_with_headers: function (url, headers) {
        serial.write('[GET/HTTP]{url:"' + url + '",headers:' + headers + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[GET/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[GET/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("GET request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // GET request with headers and return bytes
    get_request_bytes: function (url, headers) {
        serial.write('[GET/BYTES]{url:"' + url + '",headers:' + headers + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[GET/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[GET/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("GET request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // send POST request with headers
    post_request_with_headers: function (url, headers, data) {
        serial.write('[POST/HTTP]{"url":"' + url + '","headers":' + headers + ',"payload":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[POST/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[POST/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("POST request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // send PUT request with headers
    put_request_with_headers: function (url, headers, data) {
        serial.write('[PUT/HTTP]{"url":"' + url + '","headers":' + headers + ',"payload":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[PUT/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[PUT/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("PUT request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // send PATCH request with headers
    patch_request_with_headers: function (url, headers, data) {
        serial.write('[PATCH/HTTP]{"url":"' + url + '","headers":' + headers + ',"payload":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[PATCH/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[PATCH/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("PATCH request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // send DELETE request with headers
    delete_request_with_headers: function (url, headers, data) {
        serial.write('[DELETE/HTTP]{"url":"' + url + '","headers":' + headers + ',"payload":' + data + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (this.includes(sresponse, "[DELETE/SUCCESS]")) {
            while (true) {
                let line = this.read_data(500);
                if (line === "[DELETE/END]") {
                    break;
                }
                if (line !== undefined) {
                    this.clear_buffer(false); // Clear the buffer
                    return line;
                }
            }
        }
        else {
            print("DELETE request failed");
        }
        this.clear_buffer(); // Clear the buffer
        return "";
    },
    // start a WebSocket connection
    websocket_start: function (url, port, headers) {
        serial.write('[SOCKET/START]{"url":"' + url + '","port":' + port + ',"headers":' + headers + '}');
        let response = this.read_data(500);
        if (response === undefined) {
            this.clear_buffer(false); // Clear the buffer
            return false;
        }
        let sresponse = this.to_string(response);
        if (!this.includes(sresponse, "[ERROR]")) {
            this.clear_buffer(false); // Clear the buffer
            return true;
        }
        else {
            print("WebSocket connection failed");
        }
        this.clear_buffer(); // Clear the buffer
        return false;
    },
    // stop a WebSocket connection
    websocket_stop: function () {
        serial.write('[SOCKET/STOP]');
        return true;
    },
    // Helper function to check if a string contains another string
    includes: function (text, search) {
        let stringLength = text.length;
        let searchLength = search.length;
        if (stringLength < searchLength) {
            return false;
        }
        for (let i = 0; i < stringLength; i++) {
            if (text[i] === search[0]) {
                let found = true;
                for (let j = 1; j < searchLength; j++) {
                    if (text[i + j] !== search[j]) {
                        found = false;
                        break;
                    }
                }
                if (found) {
                    return true;
                }
            }
        }
    },
    // Convert an array of characters to a string
    to_string: function (text) {
        if (text === undefined) {
            return "";
        }
        let return_text = "";
        for (let i = 0; i < text.length; i++) {
            return_text += text[i];
        }
        return return_text;
    }
};
