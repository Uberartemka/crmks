import { createServer } from 'http';
import { createReadStream, existsSync } from 'fs';
import { join, extname } from 'path';
import { fileURLToPath } from 'url';
import { createProxyMiddleware } from 'http-proxy-middleware';

const __dirname = join(fileURLToPath(import.meta.url), '..');
const PORT = process.env.PORT || 4173;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// MIME types for static files
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
};

// Proxy middleware for /api/ and /kp/
const apiProxy = createProxyMiddleware({
  pathFilter: ['/api/**', '/kp/**'],
  target: BACKEND_URL,
  changeOrigin: true,
});

// Serve static files from dist/
function serveStatic(req, res) {
  let filePath = join(__dirname, 'dist', req.url === '/' ? 'index.html' : req.url);

  if (!existsSync(filePath)) {
    // SPA fallback - serve index.html for any unknown route
    filePath = join(__dirname, 'dist', 'index.html');
    if (!existsSync(filePath)) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
  }

  const ext = extname(filePath);
  const contentType = MIME[ext] || 'application/octet-stream';

  res.writeHead(200, { 'Content-Type': contentType });
  createReadStream(filePath).pipe(res);
}

// Create server
const server = createServer((req, res) => {
  const url = req.url;

  // Proxy /api/* and /kp/* to backend
  if (url.startsWith('/api/') || url.startsWith('/kp/')) {
    apiProxy(req, res);
    return;
  }

  // Serve static files
  serveStatic(req, res);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Server running on http://0.0.0.0:${PORT}`);
  console.log(`   Backend proxy: ${BACKEND_URL}`);
  console.log(`   Proxying: /api/* and /kp/* → backend`);
});
