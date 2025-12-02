#!/usr/bin/env python3
"""
Dysruption Consensus Verifier Agent (CVA) v1.0

A multi-model AI tribunal for code verification against specifications.
Uses Claude, Llama, and Gemini to evaluate code quality, security, and alignment.

Usage:
    python cva.py --dir ./my_project                    # On-demand verification
    python cva.py --dir ./my_project --watch            # Watch mode
    python cva.py --git https://github.com/user/repo    # Clone and verify
    python cva.py --help                                # Show help

Author: Dysruption
Version: 1.0
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
import yaml

# Import CVA modules
from modules.watcher import DirectoryWatcher, run_watcher
from modules.parser import ConstitutionParser, run_extraction
from modules.tribunal import Tribunal, run_adjudication, TribunalVerdict, Verdict


# Configure loguru
def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """Configure logging with loguru."""
    logger.remove()  # Remove default handler
    
    # Console handler
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    # File handler
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="7 days"
        )


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_path}. Using defaults.")
        return {}
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        logger.info(f"Loaded configuration from: {config_path}")
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}


def check_environment() -> Dict[str, bool]:
    """Check for required environment variables."""
    required_keys = {
        'OPENAI_API_KEY': 'OpenAI (GPT models)',
        'ANTHROPIC_API_KEY': 'Anthropic (Claude models)',
        'GOOGLE_API_KEY': 'Google (Gemini models)',
        'GROQ_API_KEY': 'Groq (Llama models)'
    }
    
    status = {}
    for key, desc in required_keys.items():
        present = bool(os.environ.get(key))
        status[key] = present
        if present:
            logger.debug(f"✓ {key} found ({desc})")
        else:
            logger.warning(f"✗ {key} not set ({desc} - may cause errors)")
    
    return status


def run_pipeline(
    target_dir: str,
    spec_path: str = "spec.txt",
    config_path: str = "config.yaml",
    git_url: Optional[str] = None
) -> TribunalVerdict:
    """
    Run the complete CVA pipeline.
    
    Args:
        target_dir: Directory to verify
        spec_path: Path to specification file
        config_path: Path to configuration file
        git_url: Optional Git URL to clone
        
    Returns:
        TribunalVerdict with results
    """
    logger.info("=" * 70)
    logger.info("DYSRUPTION CONSENSUS VERIFIER AGENT v1.0")
    logger.info("=" * 70)
    
    start_time = datetime.now()
    
    # Step 1: Setup watcher and build file tree
    logger.info("\n📁 STEP 1: Building File Tree")
    logger.info("-" * 40)
    
    watcher = DirectoryWatcher(target_dir, config_path)
    actual_path = watcher.setup(git_url)
    
    file_tree = watcher.build_file_tree()
    
    if not file_tree:
        logger.error("No code files found in target directory!")
        raise ValueError("Empty directory or no supported code files found")
    
    language = watcher.detect_language()
    logger.info(f"Found {len(file_tree)} code files")
    logger.info(f"Detected language: {language}")
    
    # Save file tree
    watcher.save_file_tree(file_tree)
    
    # Step 2: Extract invariants from specification
    logger.info("\n📜 STEP 2: Extracting Requirements")
    logger.info("-" * 40)
    
    # Check if spec file exists
    if not Path(spec_path).exists():
        logger.error(f"Specification file not found: {spec_path}")
        raise FileNotFoundError(f"Create {spec_path} with your project requirements")
    
    parser = ConstitutionParser(config_path)
    criteria = parser.run(spec_path)
    
    tech_count = len(criteria.get('technical', []))
    func_count = len(criteria.get('functional', []))
    logger.info(f"Extracted {tech_count} technical + {func_count} functional requirements")
    
    # Step 3: Run tribunal adjudication
    logger.info("\n⚖️ STEP 3: Tribunal Adjudication")
    logger.info("-" * 40)
    
    tribunal = Tribunal(config_path)
    verdict = tribunal.run(file_tree, criteria, language)
    
    # Step 4: Save outputs
    logger.info("\n📊 STEP 4: Generating Reports")
    logger.info("-" * 40)
    
    report_path, verdict_path = tribunal.save_outputs(verdict)
    
    # Cleanup
    watcher.cleanup()
    
    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("\n" + "=" * 70)
    logger.info("VERIFICATION COMPLETE")
    logger.info("=" * 70)
    
    verdict_emoji = {
        Verdict.PASS: "✅ PASS",
        Verdict.FAIL: "❌ FAIL",
        Verdict.PARTIAL: "⚠️ PARTIAL",
        Verdict.ERROR: "🔴 ERROR"
    }
    
    logger.info(f"Verdict: {verdict_emoji.get(verdict.overall_verdict, 'UNKNOWN')}")
    logger.info(f"Score: {verdict.overall_score}/10")
    logger.info(f"Passed: {verdict.passed_criteria}/{verdict.total_criteria}")
    logger.info(f"Static Issues: {verdict.static_analysis_issues}")
    logger.info(f"Duration: {duration:.1f}s")
    logger.info(f"Report: {report_path}")
    logger.info(f"Verdict JSON: {verdict_path}")
    logger.info("=" * 70)
    
    return verdict


def run_watch_mode(
    target_dir: str,
    spec_path: str = "spec.txt",
    config_path: str = "config.yaml",
    git_url: Optional[str] = None
):
    """
    Run CVA in watch mode, re-verifying on file changes.
    
    Args:
        target_dir: Directory to watch
        spec_path: Path to specification file
        config_path: Path to configuration file
        git_url: Optional Git URL to clone
    """
    logger.info("=" * 70)
    logger.info("DYSRUPTION CVA - WATCH MODE")
    logger.info("=" * 70)
    
    # Setup watcher
    watcher = DirectoryWatcher(target_dir, config_path)
    actual_path = watcher.setup(git_url)
    
    # Define extraction function
    def extraction_fn(file_tree: Dict[str, str]):
        parser = ConstitutionParser(config_path)
        return parser.run(spec_path)
    
    # Define adjudication function
    def adjudication_fn(file_tree: Dict[str, str], language: str):
        criteria_path = "criteria.json"
        return run_adjudication(file_tree, language, criteria_path, config_path)
    
    # Run initial verification
    logger.info("\n🔄 Running initial verification...")
    try:
        run_pipeline(target_dir, spec_path, config_path, git_url=None)  # Don't re-clone
    except Exception as e:
        logger.error(f"Initial verification failed: {e}")
    
    # Start watch loop
    logger.info(f"\n👁️ Watching {actual_path} for changes (Ctrl+C to stop)")
    logger.info(f"Debounce: 15 seconds")
    
    watcher.watch_loop(extraction_fn, adjudication_fn)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Dysruption Consensus Verifier Agent (CVA) v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cva.py --dir ./my_project                 # Verify local directory
  python cva.py --dir . --spec requirements.txt    # Custom spec file
  python cva.py --git https://github.com/user/repo # Clone and verify
  python cva.py --dir . --watch                    # Watch mode
  python cva.py --dir . --verbose                  # Verbose output

Environment Variables:
  OPENAI_API_KEY     - For GPT models
  ANTHROPIC_API_KEY  - For Claude models  
  GOOGLE_API_KEY     - For Gemini models
  GROQ_API_KEY       - For Llama models via Groq
"""
    )
    
    parser.add_argument(
        '--dir', '-d',
        type=str,
        default='.',
        help='Target directory to verify (default: current directory)'
    )
    
    parser.add_argument(
        '--git', '-g',
        type=str,
        help='Git repository URL to clone and verify'
    )
    
    parser.add_argument(
        '--spec', '-s',
        type=str,
        default='spec.txt',
        help='Path to specification file (default: spec.txt)'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--watch', '-w',
        action='store_true',
        help='Enable watch mode (re-verify on file changes)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose/debug output'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        help='Path to log file (optional)'
    )
    
    parser.add_argument(
        '--check-env',
        action='store_true',
        help='Check environment variables and exit'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Dysruption CVA v1.0'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose, args.log_file)
    
    # Check environment
    if args.check_env:
        logger.info("Checking environment variables...")
        status = check_environment()
        available = sum(1 for v in status.values() if v)
        logger.info(f"\n{available}/{len(status)} API keys configured")
        sys.exit(0)
    
    # Load configuration
    config = load_config(args.config)
    
    # Check for required API keys
    check_environment()
    
    try:
        if args.watch:
            # Watch mode
            run_watch_mode(
                target_dir=args.dir,
                spec_path=args.spec,
                config_path=args.config,
                git_url=args.git
            )
        else:
            # On-demand mode
            verdict = run_pipeline(
                target_dir=args.dir,
                spec_path=args.spec,
                config_path=args.config,
                git_url=args.git
            )
            
            # Exit code based on verdict
            if verdict.overall_verdict == Verdict.PASS:
                sys.exit(0)
            else:
                sys.exit(1)
                
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(2)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
