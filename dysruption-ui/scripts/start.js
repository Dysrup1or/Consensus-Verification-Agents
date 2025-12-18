const { spawn } = require('child_process');

const port = process.env.PORT || '3000';
const hostname = process.env.HOSTNAME;

console.log(`[start.js] Starting Next.js on port ${port}`);
console.log(`[start.js] CVA_BACKEND_URL=${process.env.CVA_BACKEND_URL || 'NOT SET'}`);
console.log(`[start.js] CVA_BACKEND_PORT=${process.env.CVA_BACKEND_PORT || 'NOT SET'}`);
console.log(`[start.js] CVA_API_TOKEN=${process.env.CVA_API_TOKEN ? 'SET' : 'NOT SET'}`);
console.log(`[start.js] NODE_ENV=${process.env.NODE_ENV || 'NOT SET'}`);

const child = spawn(
  process.execPath,
  [
    'node_modules/next/dist/bin/next',
    'start',
    '-p',
    String(port),
    ...(hostname ? ['-H', String(hostname)] : []),
  ],
  {
    stdio: 'inherit',
    env: process.env,
  }
);

// Handle SIGTERM gracefully for Railway
process.on('SIGTERM', () => {
  console.log('[start.js] Received SIGTERM, shutting down gracefully...');
  child.kill('SIGTERM');
});

process.on('SIGINT', () => {
  console.log('[start.js] Received SIGINT, shutting down gracefully...');
  child.kill('SIGINT');
});

child.on('exit', (code, signal) => {
  console.log(`[start.js] Next.js exited with code=${code} signal=${signal}`);
  if (typeof code === 'number') {
    process.exit(code);
  }
  if (signal) {
    process.exit(1);
  }
  process.exit(1);
});
