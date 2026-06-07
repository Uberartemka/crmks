import { preview } from 'vite';

const server = await preview({
  preview: {
    port: process.env.PORT || 4173,
    host: '0.0.0.0',
    allowedHosts: ['crmks-production.up.railway.app', '.railway.app', 'localhost'],
  },
  server: {
    allowedHosts: ['crmks-production.up.railway.app', '.railway.app', 'localhost'],
  },
});

server.printUrls();
server.bind();
