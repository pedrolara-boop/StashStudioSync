#!/usr/bin/env python3
"""
StashStudioMetadataMatcherPlugin

A plugin for matching studios in Stashapp database with ThePornDB and StashDB.

GitHub: https://github.com/pedrolara-boop/StashStudioMetadataMatcher
License: MIT
"""

import json
import sys
import os
import importlib.util
from stashStudioMetadataMatcher import (
    config, logger, update_all_studios, local_api_url
)

def main():
    """
    Main function for the plugin version.
    Reads plugin arguments from stdin and processes studios accordingly.
    """
    logger(f"🚀 Starting StashStudioMetadataMatcherPlugin", "INFO")
    
    # Check for plugin input from stdin
    try:
        if not sys.stdin.isatty():  # Check if stdin has data
            plugin_input = json.loads(sys.stdin.read())
            server_connection = plugin_input.get('server_connection', {})
            plugin_args = plugin_input.get('args', {})
            mode = plugin_args.get('mode', 'all')
            dry_run = plugin_args.get('dry_run', False)
            force = plugin_args.get('force', False)
            
            # Get fuzzy matching settings from plugin args if provided
            if 'fuzzy_threshold' in plugin_args:
                config['fuzzy_threshold'] = int(plugin_args['fuzzy_threshold'])
            else:
                # Use a higher threshold (95) for plugin mode by default
                config['fuzzy_threshold'] = 95
                
            if 'use_fuzzy_matching' in plugin_args:
                config['use_fuzzy_matching'] = plugin_args['use_fuzzy_matching']
            
            mode_str = " (FORCE)" if force else " (DRY RUN)" if dry_run else ""
            fuzzy_str = "" if config['use_fuzzy_matching'] else " (NO FUZZY)"
            logger(f"🚀 Running with settings{mode_str}{fuzzy_str} - Fuzzy threshold: {config['fuzzy_threshold']}", "INFO")
            
            # Default to processing all studios
            logger("🔄 Running update for all studios", "INFO")
            update_all_studios(dry_run, force)
        else:
            # No stdin data, run in batch mode
            logger("🔄 Running update for all studios in batch mode", "INFO")
            # Use a higher threshold (95) for plugin mode by default
            config['fuzzy_threshold'] = 95
            update_all_studios(False, False)  # Default to not dry run and not force
    except json.JSONDecodeError:
        logger("Failed to decode JSON input, running in batch mode", "ERROR")
        # Use a higher threshold (95) for plugin mode by default
        config['fuzzy_threshold'] = 95
        update_all_studios(False, False)  # Default to not dry run and not force
    except Exception as e:
        logger(f"Error processing plugin input: {str(e)}", "ERROR")
        # Use a higher threshold (95) for plugin mode by default
        config['fuzzy_threshold'] = 95
        update_all_studios(False, False)  # Default to not dry run and not force
        
    logger(f"✅ StashStudioMetadataMatcherPlugin completed", "INFO")

if __name__ == "__main__":
    main() 