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
import requests
from datetime import datetime
from stashapi.stashapp import StashInterface
import stashapi.log as log

# Import core functionality from the main script
# We'll only import the functions we need, not the config
from stashStudioMetadataMatcher import (
    logger, update_all_studios, update_single_studio, find_studio_by_name,
    fuzzy_match_studio_name, graphql_request, find_local_studio, get_all_studios,
    search_studio, search_tpdb_site, find_studio, find_tpdb_site,
    find_or_create_parent_studio, add_tpdb_id_to_studio, update_studio,
    update_studio_data
)

# Constants for API endpoints
TPDB_API_URL = "https://theporndb.net/graphql"
TPDB_REST_API_URL = "https://api.theporndb.net"
STASHDB_API_URL = "https://stashdb.org/graphql"

def main():
    """
    Main function for the plugin version.
    Reads plugin arguments from stdin and processes studios accordingly.
    """
    try:
        # Read the JSON input from stdin
        if not sys.stdin.isatty():  # Check if stdin has data
            plugin_input = json.loads(sys.stdin.read())
            server_connection = plugin_input.get('server_connection', {})
            plugin_args = plugin_input.get('args', {})
            
            # Create a StashInterface using the server connection details
            stash = StashInterface(server_connection)
            
            # Get the Stash configuration
            stash_config = stash.get_configuration()
            
            # Create our config dictionary
            config = {
                'scheme': server_connection.get('Scheme', 'http'),
                'host': server_connection.get('Host', 'localhost'),
                'port': server_connection.get('Port', 9999),
                'api_key': server_connection.get('ApiKey', ''),
                'tpdb_api_key': '',
                'stashdb_api_key': '',
                'log_file': 'studio_metadata_matcher.log',
                'fuzzy_threshold': 95,  # High threshold for more precise matches in plugin mode
                'use_fuzzy_matching': True,
                'stash_interface': stash,  # Store the StashInterface in the config
            }
            
            # Get API keys from Stash configuration
            if 'stashBoxes' in stash_config.get('general', {}):
                for stash_box in stash_config['general']['stashBoxes']:
                    if stash_box.get('endpoint') == TPDB_API_URL:
                        config['tpdb_api_key'] = stash_box.get('api_key', '')
                    elif stash_box.get('endpoint') == STASHDB_API_URL:
                        config['stashdb_api_key'] = stash_box.get('api_key', '')
            
            # Log the configuration (without sensitive data)
            log.info(f"🔧 Using Stash server: {config['scheme']}://{config['host']}:{config['port']}")
            log.info(f"🔧 ThePornDB API key: {'✓ Set' if config['tpdb_api_key'] else '✗ Not set'}")
            log.info(f"🔧 StashDB API key: {'✓ Set' if config['stashdb_api_key'] else '✗ Not set'}")
            
            # Build API URLs
            local_api_url = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
            
            # Get plugin arguments
            dry_run = plugin_args.get('dry_run', False)
            force = plugin_args.get('force', False)
            
            # Get fuzzy matching settings from plugin args if provided
            if 'fuzzy_threshold' in plugin_args:
                config['fuzzy_threshold'] = int(plugin_args['fuzzy_threshold'])
            
            if 'use_fuzzy_matching' in plugin_args:
                config['use_fuzzy_matching'] = plugin_args['use_fuzzy_matching']
            
            # Set up logging
            log_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(log_dir, config['log_file'])
            
            # Create a custom logger function that writes to both stashapi.log and our file
            def custom_log(message, level="INFO"):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_message = f"[{timestamp}] [{level}] {message}"
                
                # Write to our custom log file
                with open(log_path, "a") as f:
                    f.write(log_message + "\n")
                
                # Also print to console when running from command line
                print(log_message)
                
                # Also use the stashapi logging
                if level == "INFO":
                    log.info(message)
                elif level == "ERROR":
                    log.error(message)
                elif level == "DEBUG":
                    log.debug(message)
                elif level == "PROGRESS":
                    log.progress(float(message))
            
            # Override the logger from the main script
            globals()['logger'] = custom_log
            
            # Override the config and local_api_url in the imported functions
            for func in [update_all_studios, update_single_studio, find_studio_by_name,
                        fuzzy_match_studio_name, graphql_request, find_local_studio, 
                        get_all_studios, search_studio, search_tpdb_site, find_studio, 
                        find_tpdb_site, find_or_create_parent_studio, add_tpdb_id_to_studio, 
                        update_studio, update_studio_data]:
                func.__globals__['config'] = config
                func.__globals__['local_api_url'] = local_api_url
                func.__globals__['tpdb_api_url'] = TPDB_API_URL
                func.__globals__['tpdb_rest_api_url'] = TPDB_REST_API_URL
                func.__globals__['stashdb_api_url'] = STASHDB_API_URL
                func.__globals__['logger'] = custom_log
            
            # Create a wrapper for graphql_request that uses StashInterface for local requests
            original_graphql_request = graphql_request
            def wrapped_graphql_request(query, variables, endpoint, api_key, retries=5):
                # If this is a local request, use the StashInterface instead
                if endpoint == local_api_url or 'localhost' in endpoint or '127.0.0.1' in endpoint or '0.0.0.0' in endpoint:
                    try:
                        logger(f"Using StashInterface for local request", "DEBUG")
                        # Use the find/update methods of StashInterface directly instead of GraphQL
                        # This is a more reliable approach
                        
                        # For findStudio query
                        if "findStudio" in query and "id" in variables:
                            studio = stash.find_studio(variables["id"])
                            if studio:
                                return {"findStudio": studio}
                            return None
                        
                        # For allStudios query
                        elif "allStudios" in query:
                            studios = stash.find_studios()
                            if studios:
                                return {"allStudios": studios}
                            return None
                        
                        # For studioUpdate mutation
                        elif "studioUpdate" in query and "input" in variables:
                            input_data = variables["input"]
                            result = stash.update_studio(input_data)
                            if result:
                                return {"studioUpdate": result}
                            return None
                        
                        # For studioCreate mutation
                        elif "studioCreate" in query and "input" in variables:
                            input_data = variables["input"]
                            result = stash.create_studio(input_data)
                            if result:
                                return {"studioCreate": result}
                            return None
                        
                        # For any other queries, fall back to the original method
                        else:
                            logger(f"Using original graphql_request for query: {query[:50]}...", "DEBUG")
                            return original_graphql_request(query, variables, endpoint, api_key, retries)
                    except Exception as e:
                        logger(f"Error using StashInterface: {e}", "ERROR")
                        # Fall back to the original method
                        return original_graphql_request(query, variables, endpoint, api_key, retries)
                else:
                    # For external APIs, use the original method
                    return original_graphql_request(query, variables, endpoint, api_key, retries)
            
            # Replace the graphql_request function with our wrapped version
            for func in [update_all_studios, update_single_studio, find_studio_by_name,
                        fuzzy_match_studio_name, find_local_studio, get_all_studios,
                        search_studio, search_tpdb_site, find_studio, find_tpdb_site,
                        find_or_create_parent_studio, add_tpdb_id_to_studio, update_studio,
                        update_studio_data]:
                func.__globals__['graphql_request'] = wrapped_graphql_request
            
            # Log the start of the process
            mode_str = " (FORCE)" if force else " (DRY RUN)" if dry_run else ""
            fuzzy_str = "" if config['use_fuzzy_matching'] else " (NO FUZZY)"
            logger(f"🚀 Starting StashStudioMetadataMatcherPlugin{mode_str}{fuzzy_str} - Fuzzy threshold: {config['fuzzy_threshold']}", "INFO")
            
            # Process all studios (plugin only supports batch processing)
            logger("🔄 Running update for all studios", "INFO")
            update_all_studios(dry_run, force)
            
            logger(f"✅ StashStudioMetadataMatcherPlugin completed", "INFO")
        else:
            print("No input received from stdin. This script is meant to be run as a Stash plugin.")
    except json.JSONDecodeError:
        print("Failed to decode JSON input. This script is meant to be run as a Stash plugin.")
    except Exception as e:
        print(f"Error in StashStudioMetadataMatcherPlugin: {str(e)}")

if __name__ == "__main__":
    main() 