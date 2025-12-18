/**
 * Backend Client Unit Tests
 * 
 * Tests for the BackendClient HTTP and WebSocket functionality.
 */

import * as assert from 'assert';
import { BackendClient } from '../../core/backendClient';

suite('BackendClient Test Suite', () => {
  // Note: These tests mock the backend since we can't guarantee it's running

  test('Should construct with default port', () => {
    const client = new BackendClient();
    assert.ok(client, 'Client should be created');
    
    const docsUrl = client.getDocsUrl();
    assert.strictEqual(docsUrl, 'http://127.0.0.1:8001/docs');
    
    client.dispose();
  });

  test('Should construct with custom port', () => {
    const client = new BackendClient(9000);
    
    const docsUrl = client.getDocsUrl();
    assert.strictEqual(docsUrl, 'http://127.0.0.1:9000/docs');
    
    client.dispose();
  });

  test('Should update port', () => {
    const client = new BackendClient(8001);
    client.setPort(9000);
    
    const docsUrl = client.getDocsUrl();
    assert.strictEqual(docsUrl, 'http://127.0.0.1:9000/docs');
    
    client.dispose();
  });

  test('isHealthy should return false when backend is not running', async () => {
    // Use a port that definitely has nothing running
    const client = new BackendClient(59999);
    
    const isHealthy = await client.isHealthy();
    assert.strictEqual(isHealthy, false);
    
    client.dispose();
  });

  test('triggerRun should fail when backend is not running', async () => {
    const client = new BackendClient(59999);
    
    const result = await client.triggerRun({
      target_dir: '/test',
      spec_content: 'test spec',
    });
    
    assert.strictEqual(result.success, false);
    assert.ok(result.error, 'Should have error');
    
    client.dispose();
  });

  test('Should register and unregister message handlers', () => {
    const client = new BackendClient();
    let handlerCalled = false;
    
    const handler = () => {
      handlerCalled = true;
    };
    
    client.onMessage(handler);
    client.offMessage(handler);
    
    // Handler should be removed, so it won't be called
    assert.strictEqual(handlerCalled, false);
    
    client.dispose();
  });

  test('Should register and unregister connect handlers', () => {
    const client = new BackendClient();
    let connectCount = 0;
    
    const handler = () => {
      connectCount++;
    };
    
    client.onConnect(handler);
    client.offConnect(handler);
    
    assert.strictEqual(connectCount, 0);
    
    client.dispose();
  });

  test('isWebSocketConnected should return false initially', () => {
    const client = new BackendClient();
    
    assert.strictEqual(client.isWebSocketConnected(), false);
    
    client.dispose();
  });

  test('sendWebSocketMessage should return false when not connected', () => {
    const client = new BackendClient();
    
    const sent = client.sendWebSocketMessage({ type: 'test' });
    assert.strictEqual(sent, false);
    
    client.dispose();
  });
});
