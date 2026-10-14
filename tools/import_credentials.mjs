// Hidden terminal input keeps credentials out of process arguments and files.
import { spawn } from 'node:child_process';
import path from 'node:path';
if (!process.stdin.isTTY) throw new Error('Use an interactive terminal for hidden input.');
process.stdin.setRawMode(true);
process.stdin.resume();
process.stdout.write('Ready for credential JSON on stdin (input is hidden).\n');
let input = '';
process.stdin.on('data', chunk => {
  const data = chunk.toString();
  if (data.includes('\u0003')) process.exit(130);
  input += data;
  if (!/[\r\n]/.test(input)) return;
  process.stdin.setRawMode(false);
  process.stdin.pause();
  const child = spawn(path.resolve('.venv/Scripts/python.exe'), ['-m', 'jobpilot.vault', ...process.argv.slice(2)], {stdio:['pipe','inherit','inherit'], windowsHide:true});
  child.stdin.end(input.trim() + '\n');
  input = '';
  child.on('exit', code => process.exit(code ?? 1));
});
