const { spawn } = require('child_process');

const port = process.env.PORT || '3000';

const child = spawn(
  process.execPath,
  ['node_modules/next/dist/bin/next', 'start', '-p', String(port)],
  {
    stdio: 'inherit',
    env: process.env,
  }
);

child.on('exit', (code, signal) => {
  if (typeof code === 'number') {
    process.exit(code);
  }
  if (signal) {
    process.exit(1);
  }
  process.exit(1);
});
