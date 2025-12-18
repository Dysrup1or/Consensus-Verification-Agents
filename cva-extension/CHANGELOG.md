# Changelog

All notable changes to the CVA Verifier extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-12-18

### Added
- Initial release of CVA VS Code Extension
- Real-time file watching with smart debouncing
- Automatic backend startup and management
- WebSocket integration for live verification updates
- Sidebar panel showing verdict summaries and violations
- Inline diagnostics (squiggly lines) for violations
- Status bar indicator showing verification state
- Multiple commands for manual verification control
- Configurable settings for all aspects of the extension
- Bulk operation detection for AI agent workflows
- Auto-reconnection for WebSocket disconnections
- Constitution file auto-detection
- Support for custom file watch patterns
- Keyboard shortcuts for common actions

### Technical
- TypeScript implementation with strict typing
- esbuild bundling for fast builds and small package size
- Mocha test suite with VS Code extension test framework
- Comprehensive type definitions for backend communication
- Event-driven architecture with proper disposal patterns

## [Unreleased]

### Planned
- Quick fix actions for violations
- CodeLens integration for function-level verification
- Webview panel for detailed verdict reports
- Support for multiple workspaces
- Verification history and trends
- Integration with VS Code testing APIs
- Custom judge configuration UI
