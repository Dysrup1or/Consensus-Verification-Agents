/**
 * Extension Test Suite
 * 
 * Tests for the main extension functionality.
 */

import * as assert from 'assert';
import * as vscode from 'vscode';

suite('Extension Test Suite', () => {
  vscode.window.showInformationMessage('Starting CVA extension tests');

  test('Extension should be present', () => {
    const extension = vscode.extensions.getExtension('dysruption.cva-verifier');
    assert.ok(extension, 'Extension should be available');
  });

  test('Extension should have correct display name', () => {
    const extension = vscode.extensions.getExtension('dysruption.cva-verifier');
    assert.ok(extension);
    assert.strictEqual(extension.packageJSON.displayName, 'CVA - AI Code Verifier');
  });

  test('Extension commands should be registered', async () => {
    const commands = await vscode.commands.getCommands(true);
    
    const expectedCommands = [
      'cva.start',
      'cva.stop',
      'cva.restart',
      'cva.verify',
      'cva.verifyFile',
      'cva.showOutput',
      'cva.clearDiagnostics',
      'cva.openDocs',
    ];

    for (const cmd of expectedCommands) {
      assert.ok(
        commands.includes(cmd),
        `Command ${cmd} should be registered`
      );
    }
  });

  test('Extension configuration should have defaults', () => {
    const config = vscode.workspace.getConfiguration('cva');
    
    assert.strictEqual(config.get('enabled'), true, 'enabled should default to true');
    assert.strictEqual(config.get('debounceMs'), 3000, 'debounceMs should default to 3000');
    assert.strictEqual(config.get('backendPort'), 8001, 'backendPort should default to 8001');
    assert.strictEqual(config.get('autoStartBackend'), true, 'autoStartBackend should default to true');
  });

  test('Extension should have sidebar view contribution', () => {
    const extension = vscode.extensions.getExtension('dysruption.cva-verifier');
    assert.ok(extension);
    
    const views = extension.packageJSON.contributes?.views?.explorer;
    assert.ok(views, 'Should have explorer views');
    
    const cvaView = views.find((v: { id: string }) => v.id === 'cvaVerdicts');
    assert.ok(cvaView, 'Should have cvaVerdicts view');
    assert.strictEqual(cvaView.name, 'CVA Verdicts');
  });
});
