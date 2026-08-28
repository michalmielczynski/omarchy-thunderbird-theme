const NATIVE_HOST = "cloud.fifue.omarchy_thunderbird_bridge";
const RECONNECT_DELAY_MS = 5000;

let port = null;

function applyColors(colors) {
  if (!colors) return;
  browser.theme.update({ colors });
}

function connect() {
  port = browser.runtime.connectNative(NATIVE_HOST);

  port.onMessage.addListener((msg) => {
    if (msg && msg.colors) {
      applyColors(msg.colors);
    }
  });

  port.onDisconnect.addListener(() => {
    if (browser.runtime.lastError) {
      console.warn("omarchy-thunderbird-theme: native host disconnected:", browser.runtime.lastError.message);
    }
    port = null;
    setTimeout(connect, RECONNECT_DELAY_MS);
  });
}

connect();
