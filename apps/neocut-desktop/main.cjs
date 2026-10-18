const { app, BrowserWindow } = require('electron');
const path = require('node:path');
function createWindow() {
  const win = new BrowserWindow({
    width: 1440, height: 920, minWidth: 900, minHeight: 640,
    backgroundColor: '#10131b',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true }
  });
  const page = app.isPackaged
    ? path.join(process.resourcesPath, 'neocut-web', 'index.html')
    : path.join(__dirname, '../neocut-web/index.html');
  win.loadFile(page);
}
app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
