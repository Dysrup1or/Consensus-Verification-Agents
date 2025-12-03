describe('CVA Run Flow', () => {
  beforeEach(() => {
    // Assuming we run with USE_MOCK=true
    cy.visit('/', {
      onBeforeLoad(win) {
        // Force mock mode via env var simulation if possible, or rely on .env.local
        // For this test, we assume the app is started with USE_MOCK=true
      }
    });
  });

  it('shows full run lifecycle', () => {
    // 1. Initial state
    cy.contains('READY').should('exist');

    // 2. Watcher detected (mock sequence starts automatically on load in mock mode)
    cy.contains('THINKING', { timeout: 10000 }).should('exist');
    
    // 3. Scanning progress
    cy.contains('SCANNING', { timeout: 10000 }).should('exist');
    
    // 4. Final Verdict
    cy.contains('REJECTED', { timeout: 10000 }).should('exist');
    cy.contains('TRIBUNAL VERDICT').should('be.visible');

    // 5. Interact with Judge
    cy.contains('SECURITY').click();
    cy.contains('RCE risk detected').should('be.visible');

    // 6. Check Patch
    cy.contains('REMEDIATION PATCHES').should('be.visible');
    cy.get('[aria-label="Patch diff for trading/strategy.py"]').should('exist');
    
    // 7. Copy Patch
    cy.window().then((win) => {
      cy.stub(win.navigator.clipboard, 'writeText').as('copy');
    });
    cy.get('button[title="Copy Patch"]').click();
    cy.get('@copy').should('have.been.called');
  });
});
