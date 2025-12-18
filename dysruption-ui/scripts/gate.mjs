import { spawn } from 'node:child_process';

const steps = [
  ['npm', ['run', 'lint']],
  ['npm', ['run', 'typecheck']],
  ['npm', ['test']],
  ['npm', ['run', 'deps:check']],
  ['npm', ['run', 'build']],
  ['npm', ['run', 'test:e2e']],
];

function runStep(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', shell: true });
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(' ')} exited with code ${code}`));
    });
    child.on('error', reject);
  });
}

(async () => {
  try {
    for (const [command, args] of steps) {
      await runStep(command, args);
    }
  } catch (err) {
    console.error(String(err?.message || err));
    process.exit(1);
  }
})();
