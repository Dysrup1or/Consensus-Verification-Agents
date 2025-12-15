declare module 'unzipper/lib/parse' {
  import type { Transform } from 'stream';

  export default function Parse(opts?: any): Transform;
}
