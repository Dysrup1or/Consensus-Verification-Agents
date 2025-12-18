/**
 * Change Tracker Unit Tests
 * 
 * Tests for the ChangeTracker debounce and bulk detection logic.
 */

import * as assert from 'assert';
import { ChangeTracker } from '../../core/changeTracker';
import { FileChangeEvent } from '../../types';

suite('ChangeTracker Test Suite', () => {
  let tracker: ChangeTracker;
  let triggeredFiles: string[] = [];
  let triggerCount: number = 0;

  const createEvent = (filePath: string, type: 'create' | 'change' | 'delete' = 'change'): FileChangeEvent => ({
    type,
    uri: `file://${filePath}`,
    path: filePath,
    timestamp: new Date(),
  });

  setup(() => {
    triggeredFiles = [];
    triggerCount = 0;
    
    tracker = new ChangeTracker(100, (files) => {
      triggeredFiles = files;
      triggerCount++;
    });
  });

  teardown(() => {
    tracker.dispose();
  });

  test('Should add file to dirty set', () => {
    tracker.addFile(createEvent('/test/file.ts'));
    
    const dirty = tracker.getDirtyFiles();
    assert.strictEqual(dirty.length, 1);
    assert.strictEqual(dirty[0], '/test/file.ts');
  });

  test('Should not duplicate files in dirty set', () => {
    tracker.addFile(createEvent('/test/file.ts'));
    tracker.addFile(createEvent('/test/file.ts'));
    tracker.addFile(createEvent('/test/file.ts'));
    
    const dirty = tracker.getDirtyFiles();
    assert.strictEqual(dirty.length, 1);
  });

  test('Should track multiple files', () => {
    tracker.addFile(createEvent('/test/file1.ts'));
    tracker.addFile(createEvent('/test/file2.ts'));
    tracker.addFile(createEvent('/test/file3.ts'));
    
    const dirty = tracker.getDirtyFiles();
    assert.strictEqual(dirty.length, 3);
  });

  test('Should trigger after debounce period', (done) => {
    tracker.addFile(createEvent('/test/file.ts'));
    
    assert.strictEqual(triggerCount, 0, 'Should not trigger immediately');
    
    setTimeout(() => {
      assert.strictEqual(triggerCount, 1, 'Should trigger after debounce');
      assert.deepStrictEqual(triggeredFiles, ['/test/file.ts']);
      done();
    }, 150);
  });

  test('Should reset debounce on new file', (done) => {
    tracker.addFile(createEvent('/test/file1.ts'));
    
    setTimeout(() => {
      // Add another file before debounce expires
      tracker.addFile(createEvent('/test/file2.ts'));
    }, 50);

    setTimeout(() => {
      // Should not have triggered yet at 100ms
      assert.strictEqual(triggerCount, 0, 'Should not trigger while debounce is reset');
    }, 100);

    setTimeout(() => {
      // Should trigger after debounce from last file
      assert.strictEqual(triggerCount, 1, 'Should trigger once with both files');
      assert.strictEqual(triggeredFiles.length, 2);
      done();
    }, 200);
  });

  test('Should clear dirty files after trigger', (done) => {
    tracker.addFile(createEvent('/test/file.ts'));
    
    setTimeout(() => {
      assert.strictEqual(tracker.getDirtyFiles().length, 0, 'Should clear after trigger');
      done();
    }, 150);
  });

  test('Should handle deleted files separately', () => {
    tracker.addFile(createEvent('/test/file.ts', 'change'));
    tracker.addFile(createEvent('/test/deleted.ts', 'delete'));
    
    const dirty = tracker.getDirtyFiles();
    const deleted = tracker.getDeletedFiles();
    
    assert.strictEqual(dirty.length, 1);
    assert.strictEqual(deleted.length, 1);
    assert.strictEqual(deleted[0], '/test/deleted.ts');
  });

  test('Should report pending changes correctly', () => {
    assert.strictEqual(tracker.hasPendingChanges(), false);
    
    tracker.addFile(createEvent('/test/file.ts'));
    
    assert.strictEqual(tracker.hasPendingChanges(), true);
    assert.strictEqual(tracker.getPendingCount(), 1);
  });

  test('Should cancel pending verification', (done) => {
    tracker.addFile(createEvent('/test/file.ts'));
    tracker.cancel();
    
    setTimeout(() => {
      assert.strictEqual(triggerCount, 0, 'Should not trigger after cancel');
      assert.strictEqual(tracker.getDirtyFiles().length, 0, 'Should clear dirty files');
      done();
    }, 150);
  });

  test('Should force trigger immediately', (done) => {
    tracker.addFile(createEvent('/test/file.ts'));
    tracker.forceTriger();
    
    // Should trigger immediately, not after debounce
    setTimeout(() => {
      assert.strictEqual(triggerCount, 1, 'Should have triggered immediately');
    }, 10);
    
    setTimeout(() => {
      // Should not trigger again
      assert.strictEqual(triggerCount, 1, 'Should not trigger again');
      done();
    }, 150);
  });

  test('Should track statistics', (done) => {
    tracker.addFile(createEvent('/test/file1.ts'));
    
    setTimeout(() => {
      const stats = tracker.getStats();
      assert.strictEqual(stats.totalChanges, 1);
      assert.strictEqual(stats.totalTriggers, 1);
      done();
    }, 150);
  });

  test('Should update debounce time', (done) => {
    tracker.setDebounceMs(50);
    tracker.addFile(createEvent('/test/file.ts'));
    
    setTimeout(() => {
      assert.strictEqual(triggerCount, 1, 'Should trigger with new debounce time');
      done();
    }, 80);
  });
});
