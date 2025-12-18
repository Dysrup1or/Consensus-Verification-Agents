import '@testing-library/jest-dom';

import 'whatwg-fetch';

import { TextDecoder, TextEncoder } from 'util';
import { BroadcastChannel } from 'worker_threads';
import { ReadableStream, TransformStream, WritableStream } from 'stream/web';

if (!globalThis.TextEncoder) {
	(globalThis as any).TextEncoder = TextEncoder;
}

if (!globalThis.TextDecoder) {
	(globalThis as any).TextDecoder = TextDecoder;
}

if (!(globalThis as any).BroadcastChannel) {
	(globalThis as any).BroadcastChannel = BroadcastChannel;
}

if (!(globalThis as any).ReadableStream) {
	(globalThis as any).ReadableStream = ReadableStream;
}

if (!(globalThis as any).WritableStream) {
	(globalThis as any).WritableStream = WritableStream;
}

if (!(globalThis as any).TransformStream) {
	(globalThis as any).TransformStream = TransformStream;
}

let server: any;

beforeAll(async () => {
	const mod = await import('./test/msw/server');
	server = mod.server;
	server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
	server?.resetHandlers();
});

afterAll(() => {
	server?.close();
});
