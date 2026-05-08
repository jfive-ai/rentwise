// apps/desktop/main.js
//
// Phase 8 PR-A — minimal Electron shell that wraps the existing Expo web
// build as a macOS .app. The window loads the static export under
// ../web/dist/ and the FastAPI backend is expected at the URL configured
// in apps/web/app.json (`extra.apiBaseUrl`, default http://localhost:8000).
//
// We deliberately keep this tiny: no auto-update, no menus beyond the
// defaults, no native modules. The Expo web build already handles the
// service worker, manifest, and PWA hooks — Electron just gives Finder
// something to launch.

const { app, BrowserWindow, shell } = require("electron");
const path = require("node:path");

/** Returns the absolute path to the static web build that ships in the .app. */
function indexHtmlPath() {
  // In a packaged build, electron-builder copies ../web/dist under
  // <Contents/Resources>/web/dist (see `extraResources` in package.json),
  // and `process.resourcesPath` points at that Resources directory.
  // In dev (`npm start` from apps/desktop), the same relative layout works
  // off __dirname.
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "web", "dist", "index.html");
  }
  return path.join(__dirname, "..", "web", "dist", "index.html");
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 720,
    minHeight: 480,
    title: "RentWise",
    backgroundColor: "#0f172a",
    webPreferences: {
      // No preload, no node integration in the renderer — the bundled web
      // app is the same code that ships to browsers, so it should run with
      // browser-equivalent privileges.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadFile(indexHtmlPath());

  // Listing links (e.g. an open-in-source action) should open in the user's
  // default browser instead of inside the Electron window.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  // Same idea for top-level navigations to a non-file:// origin.
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://")) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
